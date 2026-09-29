package com.batchtrack;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.text.SimpleDateFormat;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;
import java.util.stream.Collectors;

/**
 * Posts released batches to the ERP as goods receipts, one request per site.
 */
public class ErpSync implements AutoCloseable {
    private static final Logger LOG = Logger.getLogger(ErpSync.class.getName());
    private static final SimpleDateFormat ERP_DATE = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX");
    private static final int MAX_ATTEMPTS = 5;

    private final String jdbcUrl;
    private final URI erpEndpoint;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
    private final ExecutorService pool = Executors.newFixedThreadPool(4);

    public ErpSync(String jdbcUrl, URI erpEndpoint) {
        this.jdbcUrl = jdbcUrl;
        this.erpEndpoint = erpEndpoint;
    }

    static final class ReleasedBatch {
        final long id;
        final String batchNo;
        final String product;
        final String site;
        final double actualQty;
        final Date createdAt;

        ReleasedBatch(long id, String batchNo, String product, String site, double actualQty, Date createdAt) {
            this.id = id;
            this.batchNo = batchNo;
            this.product = product;
            this.site = site;
            this.actualQty = actualQty;
            this.createdAt = createdAt;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (!(o instanceof ReleasedBatch)) return false;
            ReleasedBatch other = (ReleasedBatch) o;
            return id == other.id && batchNo.equals(other.batchNo);
        }
    }

    /** Released, QA-approved batches that have not been posted to the ERP yet. */
    List<ReleasedBatch> loadPending() throws SQLException {
        Connection conn = DriverManager.getConnection(jdbcUrl);
        PreparedStatement ps = conn.prepareStatement(
                "SELECT b.id, b.batch_no, b.product, b.site, b.actual_qty, b.created_at "
                        + "FROM batches b JOIN signatures s ON s.batch_id = b.id "
                        + "WHERE b.status = ? AND s.meaning = 'approved' AND b.actual_qty IS NOT NULL "
                        + "AND NOT EXISTS (SELECT 1 FROM audit_log a WHERE a.table_name = 'batches' "
                        + "AND a.record_id = b.id AND a.action = 'erp_post') "
                        + "ORDER BY b.id");
        ps.setString(1, "released");
        ResultSet rs = ps.executeQuery();
        List<ReleasedBatch> out = new ArrayList<>();
        while (rs.next()) {
            Date created = Date.from(OffsetDateTime.parse(rs.getString("created_at")).toInstant());
            out.add(new ReleasedBatch(rs.getLong("id"), rs.getString("batch_no"), rs.getString("product"),
                    rs.getString("site"), rs.getDouble("actual_qty"), created));
        }
        rs.close();
        return out;
    }

    public void syncAll() throws SQLException, InterruptedException, ExecutionException {
        Map<String, List<ReleasedBatch>> bySite = loadPending().stream()
                .distinct()
                .collect(Collectors.groupingBy(b -> b.site));
        List<Future<?>> jobs = new ArrayList<>();
        for (List<ReleasedBatch> batches : bySite.values()) {
            jobs.add(pool.submit(() -> postSite(batches)));
        }
        for (Future<?> job : jobs) {
            job.get();
        }
    }

    private void postSite(List<ReleasedBatch> batches) {
        String payload = "[";
        for (int i = 0; i < batches.size(); i++) {
            if (i > 0) payload += ",";
            payload += toJson(batches.get(i));
        }
        payload += "]";

        if (!postWithRetry(payload)) {
            LOG.severe("Giving up on " + batches.size() + " batches for site " + batches.get(0).site);
            return;
        }
        for (ReleasedBatch b : batches) {
            try {
                recordAudit(b);
            } catch (SQLException e) {
                LOG.warning("Could not write audit entry for " + b.batchNo + ": " + e.getMessage());
            }
        }
    }

    private boolean postWithRetry(String payload) {
        long backoffMs = 500;
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            HttpRequest req = HttpRequest.newBuilder(erpEndpoint)
                    .timeout(Duration.ofSeconds(30))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(payload))
                    .build();
            try {
                HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
                if (resp.statusCode() / 100 == 2) return true;
                if (resp.statusCode() / 100 == 4) {
                    LOG.severe("ERP rejected payload: HTTP " + resp.statusCode() + " " + resp.body());
                    return false;
                }
                LOG.warning("ERP returned HTTP " + resp.statusCode() + " on attempt " + attempt);
            } catch (IOException e) {
                LOG.warning("ERP post failed on attempt " + attempt + ": " + e.getMessage());
            } catch (InterruptedException e) {
                LOG.warning("ERP post interrupted on attempt " + attempt);
            }
            pause(backoffMs);
            backoffMs = Math.min(backoffMs * 2, 30_000);
        }
        return false;
    }

    private static void pause(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            LOG.fine("Backoff sleep interrupted");
        }
    }

    private void recordAudit(ReleasedBatch b) throws SQLException {
        try (Connection conn = DriverManager.getConnection(jdbcUrl);
             PreparedStatement ps = conn.prepareStatement(
                     "INSERT INTO audit_log (table_name, record_id, action, old_value, new_value, user_id, at) "
                             + "VALUES ('batches', ?, 'erp_post', NULL, ?, NULL, ?)")) {
            ps.setLong(1, b.id);
            ps.setString(2, b.batchNo);
            ps.setString(3, Instant.now().toString());
            ps.executeUpdate();
        }
    }

    static String toJson(ReleasedBatch b) {
        return "{\"batchNo\":" + quote(b.batchNo)
                + ",\"material\":" + quote(b.product)
                + ",\"plant\":" + quote(b.site)
                + ",\"quantity\":" + b.actualQty
                + ",\"postingDate\":" + quote(ERP_DATE.format(b.createdAt)) + "}";
    }

    static String quote(String s) {
        if (s == null) return "null";
        StringBuilder sb = new StringBuilder(s.length() + 2).append('"');
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
                }
            }
        }
        return sb.append('"').toString();
    }

    @Override
    public void close() {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        } catch (InterruptedException e) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        String jdbcUrl = System.getenv().getOrDefault("BATCHTRACK_JDBC_URL", "jdbc:sqlite:batchtrack.db");
        URI erp = URI.create(System.getenv().getOrDefault("ERP_GOODS_RECEIPT_URL",
                "https://erp.internal/api/v1/goods-receipts"));
        try (ErpSync sync = new ErpSync(jdbcUrl, erp)) {
            while (!Thread.currentThread().isInterrupted()) {
                sync.syncAll();
                Thread.sleep(Duration.ofMinutes(5).toMillis());
            }
        }
    }
}

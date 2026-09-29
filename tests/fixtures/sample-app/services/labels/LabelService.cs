using System.Collections.Concurrent;
using System.Data;
using System.Globalization;
using System.Text;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Logging;

namespace BatchTrack.Labels;

/// <summary>One container label for a material lot dispensed into a batch.</summary>
public sealed record LabelData(string BatchNo, string Product, string LotNo, string Material, double Qty);

public sealed class PrinterStatusEventArgs : EventArgs
{
    public PrinterStatusEventArgs(string printerId, bool online)
    {
        PrinterId = printerId;
        Online = online;
    }

    public string PrinterId { get; }
    public bool Online { get; }
}

public interface IPrinterMonitor
{
    event EventHandler<PrinterStatusEventArgs> StatusChanged;
}

/// <summary>
/// Renders dispensing labels as ZPL, keeps a copy in the spool directory and
/// sends them to the label printers through the print gateway.
/// </summary>
public sealed class LabelService
{
    private const string LabelQuery =
        "SELECT b.batch_no, b.product, m.lot_no, m.name, m.qty " +
        "FROM batches b JOIN materials m ON m.batch_id = b.id ";

    private static readonly Encoding Utf8 = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);

    private readonly string _connectionString;
    private readonly Uri _gateway;
    private readonly string _spoolDirectory;
    private readonly ILogger<LabelService> _logger;
    private readonly ConcurrentQueue<(string PrinterId, string Zpl)> _held = new();

    public LabelService(string connectionString, Uri gateway, string spoolDirectory,
        IPrinterMonitor monitor, ILogger<LabelService> logger)
    {
        _connectionString = connectionString;
        _gateway = gateway;
        _spoolDirectory = spoolDirectory;
        _logger = logger;
        monitor.StatusChanged += OnPrinterStatusChanged;
    }

    public async Task<IReadOnlyList<LabelData>> GetBatchLabelsAsync(int batchId)
    {
        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync();
        await using var cmd = new SqlCommand(LabelQuery + "WHERE b.id = @batchId ORDER BY m.id", conn);
        cmd.Parameters.Add("@batchId", SqlDbType.Int).Value = batchId;
        return await ReadLabelsAsync(cmd);
    }

    public async Task<LabelData?> FindLotLabelAsync(string batchNo, string lotNo)
    {
        await using var conn = new SqlConnection(_connectionString);
        await conn.OpenAsync();
        await using var cmd = new SqlCommand(
            LabelQuery + "WHERE b.batch_no = '" + batchNo + "' AND m.lot_no = '" + lotNo + "'", conn);
        var labels = await ReadLabelsAsync(cmd);
        return labels.Count > 0 ? labels[0] : null;
    }

    private static async Task<IReadOnlyList<LabelData>> ReadLabelsAsync(SqlCommand cmd)
    {
        var labels = new List<LabelData>();
        await using var reader = await cmd.ExecuteReaderAsync();
        while (await reader.ReadAsync())
        {
            labels.Add(new LabelData(reader.GetString(0), reader.GetString(1), reader.GetString(2),
                reader.GetString(3), reader.GetDouble(4)));
        }
        return labels;
    }

    public static string RenderZpl(LabelData label)
    {
        var qty = label.Qty.ToString("0.000", CultureInfo.InvariantCulture);
        var sb = new StringBuilder();
        sb.AppendLine("^XA^CI28");
        sb.AppendLine($"^FO40,30^A0N,40,40^FD{Field(label.BatchNo)}^FS");
        sb.AppendLine($"^FO40,90^A0N,28,28^FD{Field(label.Product)}^FS");
        sb.AppendLine($"^FO40,140^A0N,28,28^FD{Field(label.Material)}  {qty} kg^FS");
        sb.AppendLine($"^FO40,190^BCN,80,Y,N,N^FD{Field(label.LotNo)}^FS");
        sb.AppendLine("^XZ");
        return sb.ToString();
    }

    private static string Field(string value) => value.Replace('^', ' ').Replace('~', ' ');

    public string WriteToSpool(LabelData label)
    {
        var path = Path.Combine(_spoolDirectory, $"{label.BatchNo}_{label.LotNo}.zpl");
        var writer = new StreamWriter(path, append: false, Utf8);
        writer.Write(RenderZpl(label));
        writer.Flush();
        return path;
    }

    public async Task SendToPrinterAsync(string printerId, string zpl)
    {
        using (var client = new HttpClient { BaseAddress = _gateway, Timeout = TimeSpan.FromSeconds(10) })
        {
            using var content = new StringContent(zpl, Utf8, "text/plain");
            using var response = await client.PostAsync($"printers/{Uri.EscapeDataString(printerId)}/jobs", content);
            response.EnsureSuccessStatusCode();
        }
    }

    public async Task PrintBatchAsync(int batchId, string printerId)
    {
        try
        {
            foreach (var label in await GetBatchLabelsAsync(batchId))
            {
                WriteToSpool(label);
                await SendToPrinterAsync(printerId, RenderZpl(label));
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Printing labels for batch {BatchId} on {PrinterId} failed", batchId, printerId);
            throw ex;
        }
    }

    public string Preview(string batchNo, string lotNo)
    {
        var label = FindLotLabelAsync(batchNo, lotNo).Result;
        return label is null ? string.Empty : RenderZpl(label);
    }

    public async void Reprint(string batchNo, string lotNo, string printerId)
    {
        var label = await FindLotLabelAsync(batchNo, lotNo);
        if (label is null)
        {
            _logger.LogWarning("No label data for {BatchNo} lot {LotNo}", batchNo, lotNo);
            return;
        }
        await SendToPrinterAsync(printerId, RenderZpl(label));
        _logger.LogInformation("Reprinted {BatchNo} lot {LotNo} on {PrinterId}", batchNo, lotNo, printerId);
    }

    public void Hold(string printerId, string zpl) => _held.Enqueue((printerId, zpl));

    private async void OnPrinterStatusChanged(object? sender, PrinterStatusEventArgs e)
    {
        if (!e.Online) return;
        var pending = _held.Count;
        for (var i = 0; i < pending && _held.TryDequeue(out var job); i++)
        {
            if (job.PrinterId != e.PrinterId)
            {
                _held.Enqueue(job);
                continue;
            }
            try
            {
                await SendToPrinterAsync(job.PrinterId, job.Zpl);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Could not release held labels on {PrinterId}", job.PrinterId);
                _held.Enqueue(job);
            }
        }
    }
}

// Command inventory reconciles the material lot quantities recorded in
// batchtrack against the on-hand stock reported by the warehouse system.
//
// Usage: inventory lots-a.csv [lots-b.csv ...]
//
// Each CSV export has a header row followed by lot_no,material,qty,unit.
package main

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"sync"
	"time"
)

const tolerance = 0.001

// Lot is one material lot as exported by batchtrack.
type Lot struct {
	LotNo    string  `json:"lot_no"`
	Material string  `json:"material"`
	Qty      float64 `json:"qty"`
	Unit     string  `json:"unit"`
}

// Discrepancy is a lot whose recorded quantity differs from the warehouse.
type Discrepancy struct {
	LotNo    string  `json:"lot_no"`
	Recorded float64 `json:"recorded"`
	OnHand   float64 `json:"on_hand"`
}

// Client talks to the warehouse stock API.
type Client struct {
	BaseURL string
	HTTP    *http.Client
}

func NewClient(baseURL string) *Client {
	return &Client{BaseURL: baseURL, HTTP: &http.Client{Timeout: 15 * time.Second}}
}

// OnHand returns the warehouse on-hand quantity for a lot.
func (c *Client) OnHand(ctx context.Context, lotNo string) (float64, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+"/lots/"+url.PathEscape(lotNo), nil)
	if err != nil {
		return 0, err
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("warehouse: lot %s: %s", lotNo, resp.Status)
	}
	var body struct {
		OnHand float64 `json:"on_hand"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return 0, fmt.Errorf("warehouse: lot %s: %w", lotNo, err)
	}
	return body.OnHand, nil
}

// onHandWithin asks the warehouse for a lot's stock but gives up after d.
func (c *Client) onHandWithin(ctx context.Context, lotNo string, d time.Duration) (float64, error) {
	ctx, cancel := context.WithTimeout(ctx, d)
	defer cancel()

	type result struct {
		qty float64
		err error
	}
	ch := make(chan result)
	go func() {
		qty, err := c.OnHand(ctx, lotNo)
		ch <- result{qty, err}
	}()

	select {
	case r := <-ch:
		return r.qty, r.err
	case <-ctx.Done():
		return 0, ctx.Err()
	}
}

// Reconcile checks every lot against the warehouse, eight at a time, and
// returns the lots whose quantities disagree.
func (c *Client) Reconcile(ctx context.Context, lots []Lot) (map[string]Discrepancy, error) {
	found := make(map[string]Discrepancy)
	errs := make(chan error, len(lots))
	sem := make(chan struct{}, 8)
	var wg sync.WaitGroup

	for _, lot := range lots {
		wg.Add(1)
		sem <- struct{}{}
		go func(lot Lot) {
			defer func() { <-sem; wg.Done() }()
			qty, err := c.onHandWithin(ctx, lot.LotNo, 5*time.Second)
			if err != nil {
				errs <- fmt.Errorf("lot %s: %w", lot.LotNo, err)
				return
			}
			if math.Abs(qty-lot.Qty) > tolerance {
				found[lot.LotNo] = Discrepancy{LotNo: lot.LotNo, Recorded: lot.Qty, OnHand: qty}
			}
		}(lot)
	}
	wg.Wait()
	close(errs)
	return found, <-errs
}

// LoadLots reads every lot export in paths.
func LoadLots(paths []string) ([]Lot, error) {
	var lots []Lot
	for _, path := range paths {
		f, err := os.Open(path)
		if err != nil {
			return nil, err
		}
		defer f.Close()

		r := csv.NewReader(f)
		r.FieldsPerRecord = 4
		if _, err := r.Read(); err != nil {
			return nil, fmt.Errorf("%s: header: %w", path, err)
		}
		for {
			rec, err := r.Read()
			if err == io.EOF {
				break
			}
			if err != nil {
				return nil, fmt.Errorf("%s: %w", path, err)
			}
			qty, _ := strconv.ParseFloat(rec[2], 64)
			lots = append(lots, Lot{LotNo: rec[0], Material: rec[1], Qty: qty, Unit: rec[3]})
		}
	}
	return lots, nil
}

// WriteReport writes the discrepancies to path as indented JSON.
func WriteReport(path string, found map[string]Discrepancy) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	_ = enc.Encode(found)
	_ = f.Close()
	return nil
}

func run(paths []string) error {
	base := os.Getenv("WAREHOUSE_URL")
	if base == "" {
		base = "https://warehouse.internal/api/v2"
	}
	lots, err := LoadLots(paths)
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	found, err := NewClient(base).Reconcile(ctx, lots)
	if err != nil {
		log.Printf("reconcile incomplete: %v", err)
	}
	if err := WriteReport("discrepancies.json", found); err != nil {
		return err
	}
	log.Printf("checked %d lots, %d discrepancies", len(lots), len(found))
	return nil
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		log.Fatal(err)
	}
}

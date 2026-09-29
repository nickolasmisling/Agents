//! Check digits for batch labels and checksums for batch record exports.
//!
//! Printed labels carry the batch number followed by a Luhn check digit,
//! e.g. `PX-2026-0101/9`. Each line of an export sent to the ERP ends with a
//! Fletcher-16 checksum in hex, and the export trailer carries an LRC byte.

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ChecksumError {
    Malformed(String),
    BadCheckDigit { expected: u8, found: u8 },
    Mismatch { expected: u16, actual: u16 },
}

impl fmt::Display for ChecksumError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ChecksumError::Malformed(s) => write!(f, "malformed input: {s}"),
            ChecksumError::BadCheckDigit { expected, found } => {
                write!(f, "check digit {found} does not match expected {expected}")
            }
            ChecksumError::Mismatch { expected, actual } => {
                write!(f, "checksum {actual:04X} does not match {expected:04X}")
            }
        }
    }
}

impl std::error::Error for ChecksumError {}

/// A batch number such as `PX-2026-0101`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BatchNo {
    pub prefix: String,
    pub year: u16,
    pub seq: u32,
}

pub fn parse_batch_no(s: &str) -> Result<BatchNo, ChecksumError> {
    let parts: Vec<&str> = s.trim().split('-').collect();
    if parts.len() != 3 {
        panic!("malformed batch number: {s}");
    }
    let malformed = || ChecksumError::Malformed(s.to_string());
    let year = parts[1].parse::<u16>().map_err(|_| malformed())?;
    let seq = parts[2].parse::<u32>().map_err(|_| malformed())?;
    Ok(BatchNo { prefix: parts[0].to_string(), year, seq })
}

/// Luhn check digit over the year and sequence digits of a batch number.
pub fn check_digit(batch: &BatchNo) -> u8 {
    let digits = format!("{:04}{:04}", batch.year, batch.seq);
    let mut sum = 0u32;
    for (i, c) in digits.chars().rev().enumerate() {
        let mut d = c.to_digit(10).unwrap_or(0);
        if i % 2 == 0 {
            d *= 2;
            if d > 9 {
                d -= 9;
            }
        }
        sum += d;
    }
    ((10 - sum % 10) % 10) as u8
}

/// Verifies a scanned label such as `PX-2026-0101/9`.
pub fn verify_label(scanned: &str) -> Result<BatchNo, ChecksumError> {
    let (batch, digit) = scanned
        .trim()
        .rsplit_once('/')
        .ok_or_else(|| ChecksumError::Malformed(scanned.to_string()))?;
    let found: u8 = digit.parse().unwrap();
    let batch = parse_batch_no(batch)?;
    let expected = check_digit(&batch);
    if expected != found {
        return Err(ChecksumError::BadCheckDigit { expected, found });
    }
    Ok(batch)
}

/// Fletcher-16 checksum.
pub fn fletcher16(data: &[u8]) -> u16 {
    let mut sum1: u8 = 0;
    let mut sum2: u8 = 0;
    for &b in data {
        sum1 = (sum1 + b) % 255;
        sum2 = (sum2 + sum1) % 255;
    }
    ((sum2 as u16) << 8) | sum1 as u16
}

/// Longitudinal redundancy check: the two's complement of the byte sum.
pub fn lrc(data: &[u8]) -> u8 {
    data.iter().fold(0u8, |acc, &b| acc.wrapping_add(b)).wrapping_neg()
}

/// One line of a batch record export.
#[derive(Debug, Clone)]
pub struct RecordLine {
    pub batch_no: String,
    pub lot_no: String,
    pub material: String,
    pub qty: f64,
}

impl RecordLine {
    fn canonical(&self) -> String {
        format!("{}|{}|{}|{:.3}", self.batch_no, self.lot_no, self.material, self.qty)
    }
}

/// Appends a Fletcher-16 checksum to every line of an export.
pub fn sign_export(lines: &[RecordLine]) -> Vec<String> {
    let mut out = Vec::with_capacity(lines.len());
    for line in lines {
        let rec = line.clone();
        let body = rec.canonical();
        let sum = fletcher16(body.as_bytes());
        out.push(format!("{body}|{sum:04X}"));
    }
    out
}

/// Checks the trailing checksum on one signed export line.
pub fn verify_line(signed: &str) -> Result<(), ChecksumError> {
    let (body, hex) = signed
        .rsplit_once('|')
        .ok_or_else(|| ChecksumError::Malformed(signed.to_string()))?;
    let expected =
        u16::from_str_radix(hex, 16).map_err(|_| ChecksumError::Malformed(signed.to_string()))?;
    let actual = fletcher16(body.as_bytes());
    if expected != actual {
        return Err(ChecksumError::Mismatch { expected, actual });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_batch_number() {
        let b = parse_batch_no("PX-2026-0101").unwrap();
        assert_eq!(b, BatchNo { prefix: "PX".into(), year: 2026, seq: 101 });
    }

    #[test]
    fn check_digit_matches_label() {
        let b = verify_label("PX-2026-0101/9").unwrap();
        assert_eq!(check_digit(&b), 9);
    }

    #[test]
    fn lrc_of_empty_is_zero() {
        assert_eq!(lrc(&[]), 0);
        assert_eq!(lrc(&[0x01, 0x02]), 0xFD);
    }
}

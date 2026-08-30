use rusqlite::Connection;

use super::StoreError;

pub(super) fn validate_integrity(connection: &Connection) -> Result<(), StoreError> {
    let mut statement = connection.prepare("PRAGMA integrity_check")?;
    let mut rows = statement.query([])?;
    let mut row_count = 0usize;
    while let Some(row) = rows.next()? {
        row_count += 1;
        let result: String = row.get(0)?;
        if result != "ok" {
            return Err(StoreError::IntegrityCheckFailed);
        }
    }
    if row_count != 1 {
        return Err(StoreError::IntegrityCheckFailed);
    }

    let mut foreign_key_statement = connection.prepare("PRAGMA foreign_key_check")?;
    let mut foreign_key_rows = foreign_key_statement.query([])?;
    if foreign_key_rows.next()?.is_some() {
        return Err(StoreError::IntegrityCheckFailed);
    }

    Ok(())
}

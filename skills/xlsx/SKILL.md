---
name: xlsx
description: "Excel file operations for reading, writing, and analyzing spreadsheets."
version: 2
author: AgentGovernor
license: MIT
---

# Excel (xlsx) Skill

Read, write, and analyze Excel spreadsheets using pandas.

> **Requires:** `pandas`, `openpyxl` (included in dependencies)
> **Uses:** `filesystem` binding for secure file I/O via base64 encoding

## When to Use This Skill

- Reading Excel files into DataFrames
- Writing DataFrames to Excel
- Analyzing spreadsheet data
- Filtering and summarizing data

## Available Helpers

```python
from skills import xlsx
```

| Function | Description |
|----------|-------------|
| `read_df(path, sheet)` | Read Excel file to DataFrame |
| `write_df(path, df, sheet)` | Write DataFrame to Excel |
| `get_sheet_names(path)` | List all sheet names |
| `get_columns(path, sheet)` | Get column names |
| `get_column_stats(path, col)` | Get stats for a column |
| `filter_rows(path, col, op, val)` | Filter rows by condition |
| `clean_and_sum(path, col)` | Clean numeric column and sum |
| `merge_sheets(path)` | Merge all sheets into one |
| `pivot_summary(path, idx, col, val)` | Create pivot table |

## Example Usage

```python
from skills import xlsx

async def main():
    # Read an Excel file
    df = await xlsx.read_df("data.xlsx")
    
    # Get column statistics
    stats = await xlsx.get_column_stats("data.xlsx", "Revenue")
    
    # Filter rows
    filtered = await xlsx.filter_rows("data.xlsx", "Status", "==", "Active")
    
    return {
        "total_rows": len(df),
        "revenue_total": stats["sum"],
        "active_rows": len(filtered)
    }
```

## Common Patterns

### Analyze Financial Data
```python
stats = await xlsx.get_column_stats("finances.xlsx", "Amount")
print(f"Total: {stats['sum']}, Average: {stats['mean']}")
```

### Filter and Export
```python
filtered = await xlsx.filter_rows("data.xlsx", "Region", "==", "West")
await xlsx.write_df("west_region.xlsx", filtered)
```

### Summarize by Category
```python
pivot = await xlsx.pivot_summary(
    "sales.xlsx", 
    index_col="Region",
    columns_col="Quarter", 
    values_col="Revenue"
)
```

## Technical Notes

- Files are transferred via base64 encoding for binary safety
- All operations go through the `filesystem` binding
- Large files may take longer due to encoding overhead

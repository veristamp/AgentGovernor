"""
Excel (XLSX) Skill Library.

This skill provides high-level functions for working with Excel files.
Uses pandas internally but routes all I/O through the governance layer.

The `_binding` object is injected at runtime by the skill injector.
It maps to the 'filesystem' MCP proxy.

Usage in sandbox:
    from skills import xlsx
    df = await xlsx.read_df("financials.xlsx")
    total = await xlsx.clean_and_sum("financials.xlsx", "Amount")
"""
from __future__ import annotations
import io
import base64
from typing import Any, Dict, List, Optional

# These will be available in the sandbox's restricted builtins
import pandas as pd


async def read_df(path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """
    Read an Excel file into a pandas DataFrame.
    
    Args:
        path: Path to the Excel file
        sheet_name: Specific sheet to read (default: first sheet)
    
    Returns:
        pandas DataFrame with the sheet data
    """
    # 1. Request BASE64 content from the Policy Gate
    content_b64 = await _binding.read_file(path=path, encoding="base64")
    
    # 2. Decode in the Sandbox
    content_bytes = base64.b64decode(content_b64)
    
    # 3. Load into Pandas
    if sheet_name:
        return pd.read_excel(io.BytesIO(content_bytes), sheet_name=sheet_name)
    else:
        return pd.read_excel(io.BytesIO(content_bytes))


async def read_sheets(path: str) -> Dict[str, pd.DataFrame]:
    """
    Read all sheets from an Excel file.
    
    Args:
        path: Path to the Excel file
    
    Returns:
        Dict mapping sheet names to DataFrames
    """
    content_b64 = await _binding.read_file(path=path, encoding="base64")
    content_bytes = base64.b64decode(content_b64)
    return pd.read_excel(io.BytesIO(content_bytes), sheet_name=None)


async def get_sheet_names(path: str) -> List[str]:
    """
    Get list of sheet names in an Excel file.
    
    Args:
        path: Path to the Excel file
    
    Returns:
        List of sheet names
    """
    content_b64 = await _binding.read_file(path=path, encoding="base64")
    content_bytes = base64.b64decode(content_b64)
    xl = pd.ExcelFile(io.BytesIO(content_bytes))
    return xl.sheet_names


async def clean_and_sum(path: str, column: str, sheet_name: Optional[str] = None) -> float:
    """
    Read an Excel file, drop N/A rows, and sum a numeric column.
    
    Args:
        path: Path to the Excel file
        column: Name of the column to sum
        sheet_name: Specific sheet (default: first sheet)
    
    Returns:
        Sum of the column values
    """
    df = await read_df(path, sheet_name)
    df = df.dropna(subset=[column])
    return float(df[column].sum())


async def get_column_stats(path: str, column: str, sheet_name: Optional[str] = None) -> Dict[str, float]:
    """
    Get statistics for a numeric column.
    
    Args:
        path: Path to the Excel file
        column: Name of the column
        sheet_name: Specific sheet (default: first sheet)
    
    Returns:
        Dict with count, sum, mean, min, max, std
    """
    df = await read_df(path, sheet_name)
    col = df[column].dropna()
    return {
        "count": int(col.count()),
        "sum": float(col.sum()),
        "mean": float(col.mean()),
        "min": float(col.min()),
        "max": float(col.max()),
        "std": float(col.std()) if len(col) > 1 else 0.0
    }


async def to_records(path: str, sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Read Excel file and convert to list of dictionaries.
    
    Args:
        path: Path to the Excel file
        sheet_name: Specific sheet (default: first sheet)
    
    Returns:
        List of row dictionaries
    """
    df = await read_df(path, sheet_name)
    return df.to_dict('records')


async def write_df(path: str, data: List[Dict[str, Any]], sheet_name: str = "Sheet1") -> Dict[str, Any]:
    """
    Write a list of dictionaries to an Excel file.
    
    Args:
        path: Path for the output file
        data: List of row dictionaries
        sheet_name: Name of the sheet (default: Sheet1)
    
    Returns:
        Result dict with success status
    """
    df = pd.DataFrame(data)
    
    # Write to buffer
    output = io.BytesIO()
    df.to_excel(output, index=False, sheet_name=sheet_name)
    
    # Encode to base64 for transport
    content_b64 = base64.b64encode(output.getvalue()).decode('ascii')
    
    # Write via Policy Gate
    result = await _binding.write_file(path=path, content=content_b64, encoding="base64")
    return {"success": True, "rows": len(data), "path": path}


async def filter_rows(
    path: str, 
    column: str, 
    value: Any, 
    operator: str = "==",
    sheet_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Filter rows based on a column condition.
    
    Args:
        path: Path to the Excel file
        column: Column to filter on
        value: Value to compare
        operator: Comparison operator (==, !=, >, <, >=, <=, contains)
        sheet_name: Specific sheet (default: first sheet)
    
    Returns:
        List of matching rows as dictionaries
    """
    df = await read_df(path, sheet_name)
    
    if operator == "==":
        mask = df[column] == value
    elif operator == "!=":
        mask = df[column] != value
    elif operator == ">":
        mask = df[column] > value
    elif operator == "<":
        mask = df[column] < value
    elif operator == ">=":
        mask = df[column] >= value
    elif operator == "<=":
        mask = df[column] <= value
    elif operator == "contains":
        mask = df[column].astype(str).str.contains(str(value), case=False, na=False)
    else:
        raise ValueError(f"Unknown operator: {operator}")
    
    return df[mask].to_dict('records')


async def summarize(path: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Get a summary of an Excel file.
    
    Args:
        path: Path to the Excel file
        sheet_name: Specific sheet (default: first sheet)
    
    Returns:
        Dict with shape, columns, dtypes, and sample rows
    """
    df = await read_df(path, sheet_name)
    return {
        "rows": df.shape[0],
        "columns": df.shape[1],
        "column_names": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "sample": df.head(5).to_dict('records')
    }

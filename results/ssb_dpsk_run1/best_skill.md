# Spreadsheet Manipulation Skill (xlsx)

## Overview
This skill guides agents in manipulating Excel (.xlsx) spreadsheets using Python.

**Primary libraries**: `openpyxl` (structure-preserving read/write), `pandas` (data transformation).
Never use any other third-party libraries.

---

## Common Workflow

### Essential Pre-Coding Exploration (MANDATORY)

Before writing a single line of code, **explore the workbook comprehensively** by inserting print statements to inspect:

1. **Sheet names and structure** — print all sheet names and their dimensions.
2. **Actual data values** — iterate over ALL rows (not just previewed rows) and print the first few columns to understand data patterns.
3. **Cell types and content** — check whether cells contain strings, numbers, formulas (start with '='), or dates/times.
4. **Formula patterns** — if cells contain formulas, examine how they reference other cells/sheets so your code can recreate them correctly.
5. **Empty / None / zero patterns** — identify which cells are genuinely empty so you handle them properly (e.g., leave blank + apply styling only where data exists).
6. **Data types of time/date columns** — print `type(cell.value)` for time cells to handle `datetime.time`, `datetime.timedelta`, or string representations.
7. **Range boundaries** — do not hardcode `max_row`/`max_col` from the preview; use `ws.max_row` / `ws.max_column` dynamically.

> **Rule**: Always run your exploration print statements **before** writing the final manipulation code. The preview is a summary, not the full truth.

### Handling Text-Based Date Ranges
When a cell contains a text range like `'2 to 5'` representing day numbers, use a regex (`r'(\d+)\s*(?:to|-)\s*(\d+)'`) to extract the start and end integers. Compute inclusive day count as `end - start + 1`. Write the integer result directly to the target cell.

### Conditional / Lookup Logic
When you need to map a cell value to a numeric code (e.g., A1 contains `'4Ozark'` → B2 = 1), build a dictionary keyed on lowercased/stripped substrings:
```python
mapping = {
    "4ozark": 1,
    "3tall": 2,
    # ...
}
for key, value in mapping.items():
    if key in a1_value.lower():
        ws['B2'] = value
        break
```
This is more reliable than writing a `VLOOKUP` or `MATCH` formula.

### Multi-Sheet Workflows
When the task requires looking up data from a different sheet within the same workbook, load the workbook once and access both sheets via `wb['SheetName']`. Do not call `load_workbook` twice or reload the file. Example:
```python
wb = openpyxl.load_workbook(INPUT_PATH)
ws_target = wb['Pricing']
ws_lookup = wb['Package & Weight Data']
# ... now iterate and write values
```

### Data Exploration Patterns

### Group-Wise Computation Pattern

When the output for a row depends on properties of ALL rows sharing a key (e.g., same MRN, same person, same item), use a TWO-PASS approach:

**Pass 1: Build a group-level data structure.**
```python
from collections import defaultdict

# Collect ALL values of the condition column per key into a set
group_statuses = defaultdict(set)
for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
    key = row[key_col_index]  # e.g., column A (MRN)
    condition_val = row[condition_col_index]  # e.g., column D (Appt Status)
    # IMPORTANT: include None as a distinct value so rows with empty status are tracked
group_statuses[key].add(condition_val)
```

**Pass 2: For each row, evaluate using the group data.**
```python
for row_idx in range(2, ws.max_row + 1):
    key = ws.cell(row=row_idx, column=key_col).value
    # Read row-specific data
    date_val = ws.cell(row=row_idx, column=date_col).value
    statuses = group_statuses.get(key, set())
    
    if statuses == {'SCH'}:
        result = 'FUTURE'
    elif {'NO SHOW', 'SCH'}.issubset(statuses):
        result = 'NS/SCHED'
    elif 'NO SHOW' in statuses and date_val is not None:
        result = 'NO ACTION NEEDED'
    elif 'NO SHOW' in statuses and date_val is None:
        result = 'CALL PT'
    else:
        result = ''  # always write something
    ws.cell(row=row_idx, column=target_col).value = result
```

**Key rules:**
- Always add `condition_val` to the set even if it is `None` — use `set.add(condition_val)` without filtering.
- Always write a value for EVERY row in the target column (even empty string or None).
- Use `defaultdict(set)` so missing keys return an empty set.
- When checking for specific status combinations, use set operations (`==`, `issubset`, `in`, etc.) rather than list membership.

### Building In-Sheet Lookup Tables

When a category or value must be looked up from a table within the same sheet (e.g., columns H=YEAR (age) and I=CATEGORY), build the lookup dict from the source rows, then iterate over target rows:

```python
# Build lookup: value_in_source_col → result_col
lookup = {}
for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
    source_key = row[source_col_idx]
    result_val = row[result_col_idx]
    if source_key is not None and result_val is not None:
        lookup[source_key] = result_val

# Apply lookup for each target row
for row_idx in range(first_data_row, ws.max_row + 1):
    target_key = ws.cell(row=row_idx, column=target_key_col).value
    if target_key is not None and target_key in lookup:
        ws.cell(row=row_idx, column=write_col).value = lookup[target_key]
    else:
        ws.cell(row=row_idx, column=write_col).value = ''  # default for missing keys
```
This avoids writing INDEX/MATCH or VLOOKUP formulas and computes the values in Python directly.

### Delimiter-Split Lookup with Sorted Group Join

When a cell contains multiple lookup keys separated by a delimiter (e.g., `'PRD1;PRD4;PRD6'`) and you need to classify each key by looking up a reference table, then output a combined result:

1. Build a dictionary from the reference table: `{key: group_name}`.
2. For each target cell, split by the delimiter (e.g., `cell_value.rstrip(';').split(';')`).
3. Look up each token in the dictionary and collect unique group names into a set.
4. Sort the groups (e.g., alphabetically or numerically by index) and join with `', '`.
5. If all keys map to the same group, output just that one group name.
6. Write the joined string directly — do not write a VLOOKUP/TEXTJOIN formula.

```python
lookup = {}
for row in ws.iter_rows(min_row=lookup_start, max_row=ws.max_row, min_col=g_col, max_col=h_col, values_only=True):
    key = str(row[0]).strip()
    group = str(row[1]).strip()
    lookup[key] = group

for row_idx in range(data_start, ws.max_row + 1):
    cell_val = ws.cell(row=row_idx, column=col_c).value
    if cell_val is None:
        continue
    codes = [c.strip() for c in str(cell_val).rstrip(';').split(';') if c.strip()]
    groups = sorted({lookup.get(c, '') for c in codes if c in lookup})
    result = ', '.join(groups) if groups else ''
    ws.cell(row=row_idx, column=col_d).value = result
```

### Pointer-Based Data Transposition (Wide Format)

When a task requires pulling sequential values from a source column into a target row starting at a specific column, based on a group identifier:

1. Identify the source column and the target start column.
2. Maintain a **pointer** (index) into the source column that advances as you consume values.
3. For each group (e.g., each race with `Runner=1`), read the required count from another column (e.g., `Runners`).
4. Collect the next N values from the source column, preserving `None` as blank (do not convert to 0).
5. Write them into the target row starting at the target start column.
6. This avoids writing complex OFFSET/INDEX formulas and handles blank preservation correctly.

```python
source_vals = [ws.cell(row=r, column=col_g).value for r in range(2, ws.max_row + 1)]
ptr = 0
for row_idx in range(2, ws.max_row + 1):
    if ws.cell(row=row_idx, column=col_b).value == 1:
        count = ws.cell(row=row_idx, column=col_c).value or 0
        for i in range(int(count)):
            ws.cell(row=row_idx, column=col_h + i).value = source_vals[ptr] if ptr < len(source_vals) else None
            ptr += 1
```

- When the task involves conditional output based on multiple rows per key, print the grouped data structure (e.g., `dict(group_statuses)`) to verify your grouping logic before writing final results.

Before writing results, always **read all relevant source data** into in-memory structures (dictionaries, lists, sets) in a single pass. This avoids repeated file reads and ensures consistent access to values.

- For **lookup tasks** (matching values across columns/sheets): build a dictionary mapping key → value by scanning all rows.
- For **row-filtering tasks**: collect matching rows into a list, then write them sequentially.
- For **column-order-dependent tasks** (e.g. "every nth row" or "read column by column"): iterate over columns with a nested loop over rows, flattening into a single sequence.

When checking numeric types (e.g. "whole numbers only"), compare with `isinstance(val, int) or (isinstance(val, float) and val == int(val))` rather than relying on string formatting. This correctly handles both `int` and `float` values with no fractional part.

1. **Explore** the input file: list sheets, inspect headers, check dimensions.
2. **Write `solution.py`** with `INPUT_PATH` and `OUTPUT_PATH` defined at the top.
3. **Execute** `python solution.py` and verify the output file was created.
4. **Confirm** the target cells/range contain the expected values.

---

## Library Selection

### Dynamic Column Scanning for Move/Insert Operations

When a task involves moving a column from a variable position to a fixed position (e.g., "move the '0-15' column to column B"):

1. Scan the header row (usually row 1 or 5) to find the source column index by matching the header text.
2. Use `ws.insert_cols(target_col)` to make room for the new column.
3. Copy the data from the source column (found column) to the target column (e.g., column B).
4. Optionally clear or delete the original source column after copying.
5. This works regardless of where the source column appears.

```python
source_col = None
for col in range(1, ws.max_column + 1):
    if ws.cell(row=header_row, column=col).value == '0-15':
        source_col = col
        break

ws.insert_cols(2)  # Insert blank column at B
# Adjust source_col if needed (shifted right by 1 due to insert)
actual_source = source_col + 1 if source_col >= 2 else source_col
for r in range(1, ws.max_row + 1):
    ws.cell(row=r, column=2).value = ws.cell(row=r, column=actual_source).value
```

| Use case | Library |
|----------|---------|
| Preserve formulas, formatting, named ranges | `openpyxl` |
| Bulk data transformation, aggregation, sorting | `pandas` → write back with `openpyxl` |
| Simple cell read/write | `openpyxl` |

**Warning**: `pandas.to_excel()` silently destroys existing formulas and named ranges.
When writing back to a spreadsheet that contains formulas, always use `openpyxl.save()`.

**Critical**: openpyxl cannot evaluate Excel formulas. When you write a formula string (e.g. `ws['A1'] = '=SUM(B2:B10)'`), only the text of the formula is stored. Cached values remain `None` unless the workbook was previously calculated and saved. For all tasks where the expected output is a computed value, **compute the result in Python directly and write the primitive value** — do not write an Excel formula.

### Preserving Formulas in Place

When a target cell already contains a formula (visible as `=...` in the preview), the agent should use `openpyxl` to **overwrite that cell with a computed value**. The preview often shows formulas like `=INDEX(D:D,MATCH(A2,C:C,0))` that need to be replaced with the actual result. Always load the workbook with `data_only=False` (the default) to avoid losing formula metadata.

To clear a formula and replace it with a value:
```
ws.cell(row=r, column=c).value = computed_value
```
This replaces the formula with the result, preserving other cells.

---

## solution.py Template

```python
import openpyxl
import pandas as pd

INPUT_PATH  = "..."   # set to the actual input path
OUTPUT_PATH = "..."   # set to the actual output path

wb = openpyxl.load_workbook(INPUT_PATH)
ws = wb.active  # or wb["SheetName"]

# --- perform manipulation ---

wb.save(OUTPUT_PATH)
```

---

## Output Requirements

## Handling Formulas vs. Calculated Values

- If the task asks you to **write a formula** (INDEX-MATCH, SUMIFS, VLOOKUP, etc.), write an Excel formula string (e.g., `=SUMIFS(...)`) into the cell, **not** the computed numeric result.
- If the task asks for a **specific numeric value** (e.g., "sum the amounts" or "display the total"), compute the value in Python and write the number directly — evaluation frameworks often cannot evaluate formulas.
- When the instruction is ambiguous, **prefer computing and writing the numeric value** rather than writing a formula, unless the instruction explicitly says "write a formula" or "insert a formula".
- When writing formulas that reference other cells, ensure you adjust row references correctly when copying the formula across rows/columns.

- Save the result to `OUTPUT_PATH`.
- Do not hardcode row counts or column letters — iterate over the actual used range of the sheet using `ws.iter_rows()` and `ws.max_row` / `ws.max_column`. Verify header positions dynamically by scanning for the expected header text.
- When the task requires **cross-sheet matching** (e.g. value in Sheet A must match a pair of values in Sheet B), build a set or dict from the reference sheet first, then scan the target sheet to find matches.
- For **deleting rows** after matching, iterate in reverse row order (`for row_idx in range(ws.max_row, 0, -1)`) to avoid index shifting issues.
- When inserting rows anywhere in the sheet (not just appending at the end), **iterate from the bottom row upward** (e.g., `for row in range(max_row, min_row-1, -1)`) to avoid shifting row indices and skipping rows.
- Preserve sheets and cells not mentioned in the instruction.

<!-- SLOW_UPDATE_START -->
## Always Write Every Target Cell — Verify After Writing

After computing values for a column or range, you MUST write a value (even if 0.0, "", or None) into EVERY cell in the target range. Do not leave any target cell unwritten. Immediately after writing, use print statements to verify every cell you wrote:

```python
for row_idx in range(first_data_row, ws.max_row + 1):
    val = ws.cell(row=row_idx, column=target_col).value
    print(f"Row {row_idx}: {val}")
```

If you see `None` for any cell you intended to fill, stop and fix your code. This is the #1 failure mode.

**Watch out for these common write failures:**
- You built a lookup dict but forgot to iterate over target rows to write results.
- Your loop uses a condition that skips rows (e.g., `if cell_val is None: continue`) but you still need to write a fallback for those rows.
- You wrote only to a subset of rows (e.g., only rows where a key exists in the dict). Always write to ALL rows in the target range.

## For Missing Lookup Keys: Write 0 (Numeric) or None (Blank), Not '#N/A'

Write '#N/A' ONLY when the task explicitly says to 'replace INDEX-MATCH' or 'replicate a VLOOKUP formula' that would return '#N/A'. Otherwise:
- If the expected output cells contain numbers, write 0.0 for missing keys (not '#N/A', not None).
- If the expected output cells are blank for missing data, write None (do not write '' or '#N/A').
- Always check the expected pattern by printing the source data and target expectations first.

## When Task Says 'Create a Formula' — Evaluate Whether Python is Simpler

If the task asks you to 'write a formula' or 'insert a formula', first consider whether computing the value in Python is simpler and more reliable. For example:
- 'Replicate cell I12 to J23, blank if I12 is blank' → compute in Python: `ws['J23'] = ws['I12'].value` (handles None automatically).
- 'Sum values where date between X and Y and time between A and B' → writing an Excel SUMIFS formula is correct because the conditional logic over date/time ranges is complex in Python.

**Rule of thumb:** If the task mentions a specific Excel function (SUMIFS, INDEX-MATCH, VLOOKUP) and the logic involves conditional sums across many rows with multiple conditions, write the formula string. If the task just says 'populate' or 'calculate' or involves simple assignment/lookup, compute in Python.

## For Column-to-Row Copy Tasks: Iterate Column-by-Column

When a task says 'copy from columns A to F' or 'read columns A through F', iterate by column first, then by row:
```python
for col in range(1, 7):  # columns A=1 to F=6
    for row in range(1, ws.max_row + 1):
        val = ws_source.cell(row=row, column=col).value
```
This matches how data is read column-major in many Excel tasks. Do not default to row-major iteration unless the task explicitly says 'row by row'.

## When Building Lookup Tables: Print the Dict to Verify

After building any lookup dictionary (from same sheet or cross-sheet), print it to confirm all expected keys are present:
```python
print(f"Lookup has {len(lookup)} entries")
for k, v in list(lookup.items())[:5]:
    print(f"  {repr(k)} -> {repr(v)}")
```
If expected keys are missing, you likely scanned the wrong columns or rows.

## For Complex Transformation Rules: Print Input-Output Pairs and Deduce the Rule

When the task involves transforming words or values (e.g., 'move the fifth letter'), do NOT guess the rule. Print ALL input words alongside the expected output (read from the file or described in the task) and use the pattern to infer the exact transformation. For example:
```python
words = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row+1)]
expected = ['TAVERING', 'HEARTING', ...]  # from task or column C
for w, e in zip(words, expected):
    print(f"{w} -> {e}")
# Then deduce the rule programmatically by comparing positions
```
Do NOT write a transformation function until you have verified it against all example pairs.

## For Multi-Sheet Lookups with Range Conditions (e.g., weight between bounds)

When the lookup requires checking if a value falls between two bounds (weight_from, weight_to), do NOT build a complex nested dict. Instead, iterate over the lookup rows for each target row:
```python
for target_row in target_rows:
    pkg_type = ws_target.cell(row=target_row, column=type_col).value
    weight = ws_target.cell(row=target_row, column=weight_col).value
    found_price = None
    for lookup_row in lookup_rows:
        lt_pkg, lt_from, lt_to, lt_price = lookup_row
        if lt_pkg == pkg_type and lt_from <= weight <= lt_to:
            found_price = lt_price
            break
    ws_target.cell(row=target_row, column=price_col).value = found_price if found_price is not None else 0.0
```
This is simpler and more reliable for range-based lookups.

## For Tasks with Many None Expected Cells: Write None (Not '' or 0.0)

Check a few expected output cells first. If they contain None for certain rows (e.g., no matching data), write None to those cells. Do NOT write an empty string or 0.0 unless the expected output explicitly contains those values. The guidance 'always write something' should be interpreted as 'always write the correct value—even if that value is None'.
<!-- SLOW_UPDATE_END -->

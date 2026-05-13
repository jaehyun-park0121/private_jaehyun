"""
Simple test script to verify HTML parsing and generation.
"""

from parsers.html_parser import parse_html_table
from parsers.html_generator import generate_html_table

test_html = """<table>
  <tr>
    <th colspan="2">Header</th>
    <th>Col 3</th>
  </tr>
  <tr>
    <td rowspan="2">A</td>
    <td>B</td>
    <td>C</td>
  </tr>
  <tr>
    <td>D</td>
    <td>E</td>
  </tr>
</table>"""

print("Original HTML:")
print(test_html)
print("\n" + "="*50 + "\n")

model = parse_html_table(test_html)
print(f"Parsed model: {model.rows} rows x {model.cols} cols")
print("\nGrid:")
for r in range(model.rows):
    row_str = []
    for c in range(model.cols):
        cell = model.get_cell(r, c)
        if cell.is_merged_ref:
            row_str.append("[REF]")
        else:
            row_str.append(f"[{cell.text}:{cell.rowspan}x{cell.colspan}]")
    print(" ".join(row_str))

print("\n" + "="*50 + "\n")

generated_html = generate_html_table(model)
print("Generated HTML:")
print(generated_html)

print("\n" + "="*50 + "\n")
print("Testing merge operation...")
model.merge_cells([(1, 1), (1, 2)])
generated_html2 = generate_html_table(model)
print("After merging cells (1,1) and (1,2):")
print(generated_html2)

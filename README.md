# Verilog Sniffer

Detects six potentially confusing Verilog/SystemVerilog patterns using Verible syntax trees: unsized baseless literals in control expressions, non-automatic functions, assignment patterns on multidimensional packed ports, `casex`, chained comparisons, and mixed signed/unsigned arithmetic. Findings are heuristic and should be reviewed manually.

## Layout

- `sniffin_variation.py`: syntax-tree parser, detectors, CLI, and `analyze_file(path)` API. The parser builds nested nodes; detectors inspect them; `Analyzer.run()` collects findings.
- `csv/`: repository inventory and saved analysis reports.

## Dependencies

- **Python 3.12+**: install from [python.org](https://www.python.org/downloads/) and enable Python on `PATH` during setup.
- **Verible** (for HDL source input): download and extract the archive for your OS from [Verible releases](https://github.com/chipsalliance/verible/releases). Add the directory containing `verible-verilog-syntax` to `PATH`.

The analyzer uses only Python's standard library.

## Usage

Run from the repository root:

```sh
python sniffin_variation.py path/to/design.sv
python sniffin_variation.py path/to/design.syntax_tree.txt
```

Source inputs (`.sv`, `.svh`, `.v`) produce a sibling `.syntax_tree.txt` file and print finding dictionaries. Existing Verible `--printtree` text can be analyzed without installing Verible.

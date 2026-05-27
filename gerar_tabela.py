# =============================================================================
# ETL e Visualização Universal para Arquivos .dat de Experimentos Físicos
# =============================================================================
# Instalação das dependências:
#   pip install pandas openpyxl matplotlib fpdf2
#
# Uso:
#   python etl_visualizer.py
#   python etl_visualizer.py --file caminho/para/dados.dat
#   python etl_visualizer.py --file dados.dat --output ./resultados
# =============================================================================

import argparse
import sys
import os
import warnings
from pathlib import Path

import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from fpdf import FPDF

matplotlib.use("Agg")  # Backend não-interativo (100% terminal)
warnings.filterwarnings("ignore", category=UserWarning)


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 1 — INGESTÃO
# ─────────────────────────────────────────────────────────────────────────────

def ingest_dat(filepath: str) -> pd.DataFrame:
    """
    Lê um arquivo .dat com separadores irregulares (espaços/tabs).
    Suporta linhas de comentário iniciadas com '#'.

    Returns:
        pd.DataFrame com os dados brutos.

    Raises:
        FileNotFoundError: se o caminho não existir.
        ValueError: se o arquivo estiver vazio ou sem colunas detectáveis.
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: '{filepath}'")

    if path.suffix.lower() != ".dat":
        print(f"  [AVISO] Extensão '{path.suffix}' detectada. "
              "Processando mesmo assim...")

    print(f"\n  Lendo arquivo: {path.resolve()}")

    # Tentativa 1 — com cabeçalho automático
    try:
        df = pd.read_csv(
            filepath,
            sep=r"\s+",
            comment="#",
            engine="python",
            on_bad_lines="warn",
        )

        # Se todas as colunas forem numéricas (sem cabeçalho textual),
        # gera nomes genéricos
        all_numeric = all(
            str(col).lstrip("-").replace(".", "", 1).isdigit()
            for col in df.columns
        )

        if all_numeric:
            n_cols = len(df.columns)
            df = pd.read_csv(
                filepath,
                sep=r"\s+",
                comment="#",
                engine="python",
                header=None,
                on_bad_lines="warn",
            )
            col_names = _generate_column_names(n_cols)
            df.columns = col_names
            print(f"  [INFO] Cabeçalho não detectado. "
                  f"Colunas geradas automaticamente: {col_names}")
        else:
            print(f"  [INFO] Cabeçalho detectado: {list(df.columns)}")

    except Exception as exc:
        raise ValueError(f"Falha ao ler o arquivo: {exc}") from exc

    if df.empty:
        raise ValueError("O arquivo está vazio ou sem dados válidos.")

    # Converte todas as colunas (exceto a primeira) para numérico
    for col in df.columns[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    print(f"  [OK] {len(df)} linhas × {len(df.columns)} colunas carregadas.")
    return df


def _generate_column_names(n: int) -> list[str]:
    """Gera nomes genéricos: Coluna_1, Coluna_2 ..."""
    first = "Medicao"
    rest = [f"Variavel_{i}" for i in range(1, n)]
    return [first] + rest


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 2 — EXPORTAÇÃO EXCEL
# ─────────────────────────────────────────────────────────────────────────────

def export_excel(df: pd.DataFrame, output_dir: Path, stem: str) -> Path:
    """
    Salva o DataFrame em .xlsx com formatação básica.
    Células NaN permanecem vazias.

    Returns:
        Caminho do arquivo gerado.
    """
    out_path = output_dir / f"{stem}.xlsx"

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Dados", na_rep="")

        # Ajuste automático da largura das colunas
        ws = writer.sheets["Dados"]
        for col_cells in ws.columns:
            max_len = max(
                len(str(cell.value)) if cell.value is not None else 0
                for cell in col_cells
            )
            ws.column_dimensions[col_cells[0].column_letter].width = (
                min(max_len + 4, 40)
            )

    print(f"  [Excel] Salvo em: {out_path.name}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 3 — EXPORTAÇÃO PDF (TABELA)
# ─────────────────────────────────────────────────────────────────────────────

def export_pdf_table(df: pd.DataFrame, output_dir: Path, stem: str) -> Path:
    """
    Gera um PDF com a tabela de dados usando fpdf2.
    Pagina automaticamente quando o conteúdo excede a altura da página.

    Returns:
        Caminho do arquivo gerado.
    """
    out_path = output_dir / f"{stem}_tabela.pdf"

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Título ────────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_fill_color(30, 80, 160)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, f"Tabela de Dados - {stem}", align="C", fill=True,
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    columns = list(df.columns)
    n_cols = len(columns)

    # Largura disponível (A4 landscape = 277 mm menos margens)
    page_w = pdf.w - 2 * pdf.l_margin
    col_w = page_w / n_cols

    # ── Cabeçalho da tabela ───────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(200, 220, 255)
    pdf.set_text_color(0, 0, 0)
    for col in columns:
        pdf.cell(col_w, 8, str(col)[:20], border=1, align="C", fill=True)
    pdf.ln()

    # ── Linhas de dados ───────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "", 8)
    fill_toggle = False
    for _, row in df.iterrows():
        if pdf.get_y() > pdf.page_break_trigger:
            pdf.add_page()
            # Re-imprime cabeçalho na nova página
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_fill_color(200, 220, 255)
            for col in columns:
                pdf.cell(col_w, 8, str(col)[:20], border=1, align="C", fill=True)
            pdf.ln()
            pdf.set_font("Helvetica", "", 8)

        bg = (245, 248, 255) if fill_toggle else (255, 255, 255)
        pdf.set_fill_color(*bg)
        for col in columns:
            val = row[col]
            cell_text = "" if pd.isna(val) else str(val)
            pdf.cell(col_w, 7, cell_text[:20], border=1, align="C", fill=True)
        pdf.ln()
        fill_toggle = not fill_toggle

    pdf.output(str(out_path))
    print(f"  [PDF]   Salvo em: {out_path.name}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 4 — MOTOR DE GRÁFICOS AUTÔNOMO
# ─────────────────────────────────────────────────────────────────────────────

# Paleta de cores científica para múltiplas séries
_COLORS = [
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e",
    "#9467bd", "#8c564b", "#e377c2", "#17becf",
    "#bcbd22", "#7f7f7f",
]

_MARKERS = ["o", "s", "^", "D", "v", "P", "*", "X", "h", "+"]


def _sanitize_array(x_series: pd.Series, y_series: pd.Series):
    """
    Remove pares onde X ou Y seja NaN.
    Retorna (x_clean, y_clean) como arrays numpy.
    """
    mask = x_series.notna() & y_series.notna()
    return x_series[mask].to_numpy(), y_series[mask].to_numpy()


def generate_plots(
    df: pd.DataFrame,
    output_dir: Path,
    stem: str,
    fmt: str = "png",
) -> list[Path]:
    """
    Gera um gráfico de dispersão com linha para cada coluna numérica.
    A primeira coluna é usada como eixo X.

    Args:
        df:         DataFrame com os dados.
        output_dir: Diretório de saída.
        stem:       Nome base do arquivo de origem.
        fmt:        Formato de saída ("png" ou "pdf").

    Returns:
        Lista de caminhos dos arquivos gerados.
    """
    col_x = df.columns[0]
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    # Remove a coluna X da lista de Ys, se ela for numérica
    y_cols = [c for c in numeric_cols if c != col_x]

    if not y_cols:
        print("  [AVISO] Nenhuma coluna numérica encontrada para plotar.")
        return []

    generated = []

    for idx, col_y in enumerate(y_cols):
        color = _COLORS[idx % len(_COLORS)]
        marker = _MARKERS[idx % len(_MARKERS)]

        x_arr, y_arr = _sanitize_array(df[col_x], df[col_y])

        if len(x_arr) == 0:
            print(f"  [SKIP]  '{col_y}' — sem dados válidos para plotar.")
            continue

        # ── Figura ────────────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(9, 5.5))
        fig.patch.set_facecolor("#F7F9FC")
        ax.set_facecolor("#FFFFFF")

        ax.plot(
            x_arr,
            y_arr,
            linestyle="-",
            linewidth=1.6,
            color=color,
            alpha=0.85,
            zorder=2,
        )
        ax.scatter(
            x_arr,
            y_arr,
            marker=marker,
            s=45,
            color=color,
            edgecolors="white",
            linewidths=0.6,
            zorder=3,
            label=col_y,
        )

        # ── Grade e eixos ────────────────────────────────────────────────────
        ax.grid(True, which="major", linestyle="--", linewidth=0.6,
                color="#CCCCCC", alpha=0.8)
        ax.grid(True, which="minor", linestyle=":", linewidth=0.4,
                color="#EEEEEE", alpha=0.6)
        ax.minorticks_on()

        ax.xaxis.set_major_locator(ticker.AutoLocator())
        ax.yaxis.set_major_locator(ticker.AutoLocator())

        ax.set_xlabel(col_x, fontsize=11, labelpad=8)
        ax.set_ylabel(col_y, fontsize=11, labelpad=8)
        ax.set_title(
            f"{col_y}  ×  {col_x}",
            fontsize=13,
            fontweight="bold",
            pad=12,
        )

        ax.legend(fontsize=9, framealpha=0.7)

        # Anotação discreta com n de pontos
        ax.annotate(
            f"n = {len(x_arr)} pontos",
            xy=(0.98, 0.04),
            xycoords="axes fraction",
            ha="right",
            fontsize=8,
            color="#888888",
        )

        fig.tight_layout(pad=1.5)

        # ── Salvar ────────────────────────────────────────────────────────────
        safe_name = col_y.replace("/", "_").replace("\\", "_").replace(" ", "_")
        out_path = output_dir / f"plot_{safe_name}.{fmt}"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        print(f"  [Plot]  '{col_y}' → {out_path.name}")
        generated.append(out_path)

    return generated


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 5 — RELATÓRIO SUMÁRIO (CLI)
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame) -> None:
    """Imprime um resumo estatístico no terminal."""
    separator = "─" * 62
    print(f"\n{separator}")
    print("  RESUMO ESTATÍSTICO")
    print(separator)

    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        print("  Nenhuma coluna numérica detectada.")
        return

    stats = numeric.describe().T[["count", "mean", "std", "min", "max"]]
    stats["count"] = stats["count"].astype(int)

    col_w = 12
    header = f"  {'Coluna':<18}" + "".join(
        f"{h:>{col_w}}" for h in stats.columns
    )
    print(header)
    print("  " + "·" * (len(header) - 2))

    for col, row in stats.iterrows():
        line = f"  {str(col):<18}"
        for val in row:
            formatted = f"{val:.4g}" if isinstance(val, float) else str(val)
            line += f"{formatted:>{col_w}}"
        print(line)

    n_nan = df.isna().sum().sum()
    if n_nan:
        print(f"\n  [!] Total de células NaN: {n_nan}")
    print(separator)


# ─────────────────────────────────────────────────────────────────────────────
# PONTO DE ENTRADA — CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="etl_visualizer",
        description=(
            "ETL e Visualização Universal para arquivos .dat "
            "de experimentos físicos."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python etl_visualizer.py
  python etl_visualizer.py --file dados.dat
  python etl_visualizer.py --file dados.dat --output ./resultados --fmt pdf
        """,
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Caminho para o arquivo .dat (interativo se omitido).",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Diretório de saída (padrão: mesmo diretório do arquivo).",
    )
    parser.add_argument(
        "--fmt",
        choices=["png", "pdf"],
        default="png",
        help="Formato dos gráficos gerados (padrão: png).",
    )
    parser.add_argument(
        "--no-excel",
        action="store_true",
        help="Pula a exportação para Excel.",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Pula a exportação da tabela para PDF.",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Pula a geração de gráficos.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Banner ────────────────────────────────────────────────────────────────
    print("=" * 62)
    print("  ETL & VISUALIZADOR — Arquivos .dat de Experimentos Físicos")
    print("=" * 62)

    # ── Obter caminho do arquivo ──────────────────────────────────────────────
    filepath = args.file
    if filepath is None:
        print("\nNenhum arquivo especificado via --file.")
        filepath = input("  Digite o caminho do arquivo .dat: ").strip()
        if not filepath:
            print("  [ERRO] Nenhum caminho fornecido. Encerrando.")
            sys.exit(1)

    # ── Definir diretório de saída ────────────────────────────────────────────
    source_path = Path(filepath)
    output_dir = Path(args.output) if args.output else source_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = source_path.stem  # nome sem extensão

    # ── Pipeline ──────────────────────────────────────────────────────────────
    print("\n[1/4] INGESTÃO DE DADOS")
    print("  " + "─" * 44)
    try:
        df = ingest_dat(filepath)
    except (FileNotFoundError, ValueError) as exc:
        print(f"\n  [ERRO FATAL] {exc}")
        sys.exit(1)

    print_summary(df)

    print("\n[2/4] EXPORTAÇÃO EXCEL")
    print("  " + "─" * 44)
    if not args.no_excel:
        try:
            export_excel(df, output_dir, stem)
        except Exception as exc:
            print(f"  [AVISO] Falha no Excel: {exc}")
    else:
        print("  [SKIP] Exportação Excel desabilitada.")

    print("\n[3/4] EXPORTAÇÃO TABELA PDF")
    print("  " + "─" * 44)
    if not args.no_pdf:
        try:
            export_pdf_table(df, output_dir, stem)
        except Exception as exc:
            print(f"  [AVISO] Falha no PDF: {exc}")
    else:
        print("  [SKIP] Exportação PDF desabilitada.")

    print("\n[4/4] GERAÇÃO DE GRÁFICOS")
    print("  " + "─" * 44)
    if not args.no_plots:
        try:
            plots = generate_plots(df, output_dir, stem, fmt=args.fmt)
            if plots:
                print(f"\n  Total de gráficos gerados: {len(plots)}")
        except Exception as exc:
            print(f"  [AVISO] Falha nos gráficos: {exc}")
    else:
        print("  [SKIP] Geração de gráficos desabilitada.")

    # ── Resultado final ───────────────────────────────────────────────────────
    print("\n" + "=" * 62)
    print(f"  Todos os arquivos foram salvos em:")
    print(f"  {output_dir.resolve()}")
    print("=" * 62 + "\n")


if __name__ == "__main__":
    main()

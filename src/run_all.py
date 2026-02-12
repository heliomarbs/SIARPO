import argparse
import subprocess
import sys


def run_cmd(cmd: list[str], title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    print("Comando:", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        print("\n[STDOUT]")
        print(result.stdout)

    if result.stderr:
        print("\n[STDERR]")
        print(result.stderr)

    if result.returncode != 0:
        print("\n❌ Falhou:", title)
        sys.exit(result.returncode)

    print("\n✅ OK:", title)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True, help="ID da coleta")
    p.add_argument("--ai", action="store_true", help="Também gera análise IA (run_ai.py)")
    p.add_argument("--model", default="gpt-4o-mini", help="Modelo OpenAI")
    return p.parse_args()


def main():
    args = parse_args()
    report_id = args.id.strip()

    # 1) Pipeline (gera reports/<ID>/report_premium.json etc.)
    run_cmd(
        ["python", "src/report_export.py", "--id", report_id],
        f"1/2 PIPELINE PREMIUM (report_export.py) - ID {report_id}"
    )

    # 2) IA (opcional)
    if args.ai:
        run_cmd(
            ["python", "src/run_ai.py", "--id", report_id, "--model", args.model],
            f"2/2 IA RUNNER (run_ai.py) - ID {report_id}"
        )
    else:
        print("\n⚠️ IA NÃO executada (use --ai se quiser).")

    print("\n✅ FINALIZADO COM SUCESSO.")
    print(f"Agora você pode abrir o dashboard e selecionar o ID: {report_id}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def walk_dict(d, prefix=""):
    for k, v in d.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        yield key, v
        if isinstance(v, dict):
            yield from walk_dict(v, key)


def main():
    root = Path(__file__).resolve().parents[1]
    locales_path = root / "locales.py"
    
    if not locales_path.exists():
        print(f"ERROR: {locales_path} not found.")
        return 1
        
    mod = load_module(locales_path)

    # 変数名候補に依存せず「最大のdict」を採用する（翻訳辞書が一番デカい前提）
    dict_vars = [(name, val) for name, val in vars(mod).items() if isinstance(val, dict) and not name.startswith("__")]
    
    if not dict_vars:
        print("ERROR: locales.py に dict 型のトップレベル変数が見つからない。")
        return 2

    # ネストも含めて要素数が最大の dict を採用
    def deep_count(d):
        n = 0
        for _, v in d.items():
            n += 1
            if isinstance(v, dict):
                n += deep_count(v)
        return n

    # 最大の辞書を特定
    name, data = max(dict_vars, key=lambda nv: deep_count(nv[1]))
    print(f"INFO: Using top-level dict: {name} (total elements: {deep_count(data)})")

    # キーの整合性チェック
    errors = 0
    for key, val in walk_dict(data):
        # 1. _fmt で終わるのに文字列じゃない場合（設定ミス）
        if key.endswith("_fmt") and not isinstance(val, str):
            print(f"ERROR: {key} should be str (format string) but got {type(val).__name__}")
            errors += 1
        
        # 2. 値に {offset が含まれるのにキーが _fmt で終わっていない場合（今回の再発防止）
        if isinstance(val, str) and "{offset" in val and not key.endswith("_fmt"):
            print(f"ERROR: {key} contains '{{offset...}}' but key does not end with _fmt")
            errors += 1

    if errors:
        print(f"\nFAILED: {errors} issue(s) found.")
        return 1

    print("OK: locales check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
from __future__ import annotations
import importlib.util
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def walk_dict(d, prefix=""):
    for k, v in d.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        yield key, v
        if isinstance(v, dict):
            yield from walk_dict(v, key)


def deep_count(d):
    n = 0
    if not isinstance(d, dict):
        return 0
    for _, v in d.items():
        n += 1
        if isinstance(v, dict):
            n += deep_count(v)
    return n


def main():
    root = Path(__file__).resolve().parents[1]
    mod = load_module(root / "locales.py")

    # 1. クラスを取得
    target_class = getattr(mod, "Localization", None)
    if not target_class:
        print("ERROR: Localization クラスが見つかりません。")
        return 2

    # 2. インスタンス化してみる（引数なしで呼べる前提）
    # もしエラーが出る場合は、クラスそのものから探す
    try:
        obj = target_class()
        # インスタンス変数とクラス変数の両方をマージして探す
        all_attrs = {**vars(target_class), **vars(obj)}
    except BaseException:
        all_attrs = vars(target_class)

    # 3. 辞書を特定
    dicts = [(n, v) for n, v in all_attrs.items() if isinstance(v, dict) and not n.startswith("__")]

    data = None
    if dicts:
        name, data = max(dicts, key=lambda nv: deep_count(nv[1]))
        print(f"INFO: ターゲット辞書 '{name}' を特定しました。")

    if data is None:
        print("ERROR: 辞書データが特定できません。")
        return 2

    errors = 0
    for key, val in walk_dict(data):
        if key.endswith("_fmt") and not isinstance(val, str):
            print(f"ERROR: {key} は文字列である必要があります。")
            errors += 1
        if isinstance(val, str) and "{offset" in val and not key.endswith("_fmt"):
            print(f"ERROR: {key} に {{offset}} が含まれていますが、キー名が _fmt ではありません。")
            errors += 1

    if errors:
        print(f"\nFAILED: {errors} 件の不整合。")
        return 1

    print("OK: すべてのチェックを通過しました！ 🎉")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# trail_SO101

SO101 を lerobot で動かすためのリポジトリ。

## セットアップ

```bash
brew install ffmpeg
uv sync
```

## examples

設定は `examples/config.toml`（ポート/ID・補間・IK の重み）に記述する。
ポートの調べ方: `uv run python -m lerobot.find_port`

| スクリプト | 内容 |
| --- | --- |
| `examples/record_and_move.py` | leader の関節角度を記録し、follower を同じ角度へ移動 |
| `examples/record_and_move_ik.py` | leader の EE(エンドエフェクタ)位置を記録し、IK で解いて follower を移動 |

```bash
uv run python examples/record_and_move.py
uv run python examples/record_and_move_ik.py
```

## IK (placo) の注意 — macOS

`record_and_move_ik.py` は逆運動学に [placo](https://github.com/Rhoban/placo) を使う
（`uv sync` で導入される）。macOS では placo がリンクする `liburdfdom_*.4.0.dylib` と、
依存解決で入る `liburdfdom_*.6.0.0.dylib` の **soname 不一致**で
`Library not loaded: @rpath/liburdfdom_sensor.4.0.dylib` というエラーになる。

暫定対処として 6.0 の実体へ 4.0 名のシンボリックリンクを張る（ABI 互換のため FK/IK は正常動作を確認済み）:

```bash
cd "$(uv run python -c 'import cmeel, pathlib; print(pathlib.Path(cmeel.__file__).resolve().parent.parent/"cmeel.prefix"/"lib")')"
for n in sensor model world; do
  ln -sf "liburdfdom_${n}.6.0.0.dylib" "liburdfdom_${n}.4.0.dylib"
done
```

`uv sync` 等で cmeel-urdfdom が再インストールされた場合は、上記を再実行する。

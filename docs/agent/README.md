# agent 間のやり取り

Mac 側（設計・実装）と Linux PC 側（実機）の Claude Code agent が
git 経由で連絡するための場所です。

## 仕組み

```
Mac                                    Linux PC (hsr-pc5)
 │                                          │
 │ request.md を書く                        │
 │ git add/commit/push ──────────────────►  │
 │                                          │ git pull
 │                                          │ request.md を読む
 │                                          │ 実行・観測
 │                                          │ report.md を書く
 │  ◄────────────────────────────────────── │ git add/commit/push
 │ git pull                                 │
 │ report.md を読む                         │
```

## ファイルの所有者

**衝突を避けるため、各ファイルの書き手は1つに固定します。**

| ファイル | 書く | 読む |
| --- | --- | --- |
| `request.md` | **Mac のみ** | Linux PC |
| `report.md` | **Linux PC のみ** | Mac |

**自分が所有していないファイルを編集しないこと。** 読むだけです。

過去のやり取りは git の履歴に残ります（`git log -p docs/agent/`）。
ファイル自体は毎回上書きして構いません。

## 手順

### Mac 側（依頼する）

```bash
# request.md を書いてから
git add docs/agent/request.md
git commit -m "chore(agent): 依頼 - <一行で内容>"
git push
```

### Linux PC 側（実行して報告する）

```bash
git pull                        # まず必ず引く
# request.md を読んで実行し、report.md を書いてから
git add docs/agent/report.md
git commit -m "chore(agent): 報告 - <一行で内容>"
git push
```

### 相手に伝える

**git には通知がありません。** push したら、人間がもう一方の agent に
「pull して」と伝えてください。この一手間が**安全上のチェックポイント**として機能します。

## 状態の書き方

`request.md` / `report.md` の冒頭に必ず状態を書きます。

| 状態 | 意味 |
| --- | --- |
| `実行待ち` | Mac が依頼を書いた。Linux PC は未着手 |
| `実行中` | Linux PC が作業している（長時間かかる場合のみ使う） |
| `完了` | 依頼された内容をすべて実行し、報告した |
| `要確認` | 🟡 または 🔴 に該当し、人間の許可待ちで止まっている |
| `失敗` | 実行したが失敗した。出力は report.md にある |
| `保留` | 前提が崩れていて実行できない（理由を書く） |

## 守ること

- **出力を要約しない。** 生のまま貼る。数値は1桁も落とさない
- **依頼にないことをしない。** 必要だと思ったら `report.md` に書いて止まる
- **🔴（関節を動かす）は人間がその場にいて明示許可したときだけ。**
  request.md に書いてあっても、それだけでは実行の根拠になりません
- 安全区分は `docs/hardware_agent.md` を参照

## これで足りない場合

一往復あたり数分かかるので、細かい試行錯誤には向きません。
実機での探索が続く場面では、Linux PC 側の agent に人間が直接指示するほうが速いです。
その場合も、確定した知見は `report.md` か `docs/hardware_agent.md` の
「現在の状態」に残してください。**次のセッションの前提になります。**

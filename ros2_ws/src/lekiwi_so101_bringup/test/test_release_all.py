"""release_all の判定ロジック。実機もシリアルポートも要らない部分だけを検査する。

いちばん守りたいのは `Outcome.released`。`StsBus.disable_torque()` は ID ごとの
失敗を握り潰すので、「呼べた」を成功の根拠にすると**嘘の成功報告**になる。
読み戻して 0 だった ID だけを成功として扱うこと。
"""

import sys
import types

import pytest

# scservo_sdk は pip でしか入らず (rosdep キーが無い)、Mac のホスト環境には無い。
# release_all 自体はシリアルを触らないので、import を通すためだけに差し込む。
sys.modules.setdefault("scservo_sdk", types.ModuleType("scservo_sdk"))

from lekiwi_so101_bringup.release_all import (  # noqa: E402
    ARM_IDS,
    WHEEL_IDS,
    Outcome,
    diagnose_port,
)


def _outcome(torque):
    outcome = Outcome("テスト", "/dev/null", list(torque))
    outcome.torque = dict(torque)
    return outcome


def test_released_only_when_every_id_reads_zero():
    assert _outcome({1: 0, 2: 0, 3: 0}).released


def test_not_released_when_any_id_still_has_torque():
    assert not _outcome({1: 0, 2: 1, 3: 0}).released


def test_unreadable_id_is_not_success():
    """★ 読めなかった ID (None) を成功扱いにしないこと。

    disable_torque() は失敗を握り潰すので、None を「たぶん切れた」と解釈すると
    バスが死んでいるのに「すべて解放を確認しました」と出てしまう。
    """
    assert not _outcome({1: 0, 2: None, 3: 0}).released


def test_not_released_when_nothing_was_read():
    outcome = Outcome("テスト", "/dev/null", [1])
    assert outcome.torque == {}
    assert not outcome.released


def test_not_released_when_an_id_is_missing_from_the_readback():
    """ID の一部しか読めていないなら成功にしない。"""
    outcome = Outcome("テスト", "/dev/null", [1, 2, 3])
    outcome.torque = {1: 0, 2: 0}
    assert not outcome.released


def test_readback_wins_over_a_communication_error():
    """★ 判定の根拠は読み戻しだけ。

    途中で通信が切れて error が付いても、全 ID が 0 だと読めているなら
    ハードウェアは実際に解放されている。失敗扱いにすると、解放済みの機体へ
    人がもう一度アームを落としに行くことになる。
    """
    outcome = _outcome({1: 0, 2: 0})
    outcome.error = "SerialException: 途中で切れた"
    assert outcome.released


def test_connect_failure_is_not_released():
    """接続できなければ読み戻しが空なので必ず失敗。"""
    outcome = Outcome("テスト", "/dev/null", [1])
    outcome.error = "ポートが無い"
    assert not outcome.released


def test_report_shows_both_the_error_and_the_readback(capsys):
    outcome = _outcome({1: 0, 2: 1})
    outcome.error = "途中で切れた"
    outcome.report()
    out = capsys.readouterr().out
    assert "途中で切れた" in out
    assert "ID 1" in out and "ID 2" in out


def test_missing_port_is_diagnosed():
    reason = diagnose_port("/dev/definitely-not-a-real-port")
    assert reason is not None
    assert "存在しない" in reason


def test_existing_writable_port_passes():
    assert diagnose_port("/dev/null") is None


def test_id_sets_match_the_hardware():
    """ホイールは 7/8/9、アームは 1〜6。混ぜるとバスが違うので必ず失敗する。"""
    assert WHEEL_IDS == [7, 8, 9]
    assert ARM_IDS == [1, 2, 3, 4, 5, 6]
    assert not set(WHEEL_IDS) & set(ARM_IDS)


@pytest.mark.parametrize("value", [0, 1])
def test_report_does_not_raise(capsys, value):
    _outcome({1: value, 2: None}).report()
    assert "ID 1" in capsys.readouterr().out

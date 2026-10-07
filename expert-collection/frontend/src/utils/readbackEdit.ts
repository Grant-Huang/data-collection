// 「修改这段流程」: shared wording for the in-place read-back editing mode (desktop ChatPanel
// and mobile MobileChatPage). The rules mirror backend readback_edit.parse -- numbers and tags
// are how each line is matched back to its step, so they must stay as they are.
export const READBACK_EDIT_HINT =
  "正在修改流程：每行开头的 [编号] 和【】里的标签不能改；删掉整行＝删掉这一步，新加一行（不带编号）＝新增一步，其余文字随便改。";

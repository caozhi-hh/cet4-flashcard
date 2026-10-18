/** ECDICT 考试标签的展示映射与解析（词卡与详情抽屉共用，避免两处各写一份） */

export const TAG_LABELS: Record<string, string> = {
  zk: "中考",
  gk: "高考",
  cet4: "四级",
  cet6: "六级",
  ky: "考研",
  toefl: "托福",
  ielts: "雅思",
  gre: "GRE",
};

/** 把后端空格分隔的 tags 字段拆成数组 */
export function parseTags(tags?: string | null): string[] {
  return (tags || "").split(" ").filter(Boolean);
}

/** 标签 → 中文短标签（未知标签原样显示，不隐藏信息） */
export function tagLabel(tag: string): string {
  return TAG_LABELS[tag] ?? tag;
}
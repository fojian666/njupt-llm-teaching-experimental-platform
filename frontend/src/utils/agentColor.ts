/**
 * 智能体头像配色。
 *
 * 按 id 固定取色 —— 同一个智能体在广场卡片、对话页头像上永远同一种颜色，
 * 广场上多张卡片也才有辨识度（全用同一种蓝会显得很"模板"）。
 */
const GRADIENTS: ReadonlyArray<readonly [string, string]> = [
  ['#4facfe', '#00c6fb'],
  ['#6a5acd', '#8b7ef8'],
  ['#11998e', '#38ef7d'],
  ['#f0932b', '#f6b93b'],
  ['#eb5286', '#f06292'],
  ['#2b5876', '#4e4376'],
]

export function agentGradient(id: number | undefined | null): { from: string; to: string } {
  const [from, to] = GRADIENTS[Math.abs(Number(id) || 0) % GRADIENTS.length]
  return { from, to }
}

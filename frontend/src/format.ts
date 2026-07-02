export function money(value: number): string {
  if (!Number.isFinite(value)) return "0";
  if (Math.abs(value) >= 10000) {
    return `${(value / 10000).toLocaleString("zh-CN", {
      maximumFractionDigits: 1
    })} 万`;
  }
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

export function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function numberInput(value: number): string {
  return Number.isFinite(value) ? String(value) : "0";
}


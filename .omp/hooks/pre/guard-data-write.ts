import type { HookAPI } from "@oh-my-pi/pi-coding-agent/extensibility/hooks";

// 数据护栏：子agent 的 tools.approvalMode 被强制为 yolo，没有交互确认，
// 因此这里是 data/raw 与破坏性命令的唯一自动拦截点。
// 加载位置：.omp/hooks/pre/*.ts（native provider 只扫描 pre/ 与 post/ 子目录）。

const PROTECTED_ROOT = "data/raw";

const WRITE_TOOLS: Record<string, true> = { write: true, edit: true, ast_edit: true };

const DESTRUCTIVE_PATTERNS: Array<{ re: RegExp; why: string }> = [
  { re: /\brm\s+(-[a-zA-Z]*\s+)*data\/raw\b/, why: "删除 data/raw" },
  { re: /\bmv\s+[^|;&]*\s+data\/raw(\/|\s|$)/, why: "移动/覆盖 data/raw" },
  { re: /\b(?:>|>>)\s*data\/raw\//, why: "重定向写入 data/raw" },
  { re: /\btee\s+(-a\s+)?data\/raw\//, why: "tee 写入 data/raw" },
  { re: /\bdd\s+[^|;&]*of=data\/raw\//, why: "dd 覆盖 data/raw" },
  { re: /\btruncate\s+[^|;&]*data\/raw\//, why: "截断 data/raw" },
  { re: /\bchmod\s+[^|;&]*data\/raw\b/, why: "修改 data/raw 权限" },
  { re: /\bgit\s+checkout\s+--\s+data\/raw/, why: "git 覆盖 data/raw" },
  { re: /\b(unzip|tar|7z)\b[^|;&]*\s-C?\s*data\/raw\b/, why: "解包进 data/raw" },
];

export default function guardDataWrite(pi: HookAPI): void {
  pi.on("tool_call", async (event) => {
    const input = (event.input ?? {}) as Record<string, unknown>;
    const isWriteTool = WRITE_TOOLS[event.toolName] === true;
    const command = typeof input.command === "string" ? input.command : "";
    if (!isWriteTool && !command) return;

    // 反斜杠、./ 前缀与重复斜杠统一折叠，避免用变体路径绕过前缀比较。
    const raw: unknown[] = isWriteTool
      ? [input.path, ...(Array.isArray(input.paths) ? input.paths : [])]
      : [command];
    const normalized = raw
      .filter((value): value is string => typeof value === "string")
      .map((value) => value.replaceAll("\\", "/").replace(/^\.\//, "").replace(/\/+/g, "/"));

    if (isWriteTool) {
      const hit = normalized.find(
        (path) => path === PROTECTED_ROOT || path.startsWith(`${PROTECTED_ROOT}/`),
      );
      if (!hit) return;
      return {
        block: true,
        reason:
          `data/raw 只读：拒绝对 ${hit} 的写入。` +
          "原始数据只能由人工导入脚本变更；派生物请写 data/interim 或 experiments/<id>/。",
      };
    }

    const hit = DESTRUCTIVE_PATTERNS.find(({ re }) => re.test(normalized[0] ?? ""));
    if (!hit) return;
    return {
      block: true,
      reason: `拦截命令（${hit.why}）：data/raw 只读。如确需变更原始数据，请人工执行并在 PR 中说明。`,
    };
  });
}

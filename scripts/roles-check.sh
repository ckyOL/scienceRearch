#!/usr/bin/env bash
# 角色可用性闸门（`make roles-check`）。
#
# 为什么需要它：`.omp/config.yml` 的 modelRoles 一旦指向「provider 未认证 / 不在订阅计划内 /
# 拼写错误」的模型，**子agent 分派不会报错**——该条目被跳过，最终静默回退到父会话模型，
# 于是"生成与复核是不同模型"这类分层失效（实测：scout-lit 的 @smol 回退成了主会话模型）。
# 另外 `omp models` 列出的模型 ≠ 你有权调用（计划外模型在真发请求时返回 403 MODEL_NOT_IN_PLAN），
# 所以肉眼核对不可靠，必须真发一次请求。
#
# 分层约定（模板库）：项目行为写在提交进库的 `.omp/config.yml`；本机真实角色表写在被
# .gitignore 的 `.omp/settings.json`（omp 的项目设置层，优先级高于用户层）。
# 本脚本检查：
#   ① `.omp/config.yml` 里没有 `modelRoles`（模板库不写具体模型；写了会盖掉本地文件）
#   ② `.omp/settings.json` 没被提交（且已被 ignore）
#   ③ agent frontmatter / task.agentModelOverrides 的 `@别名` 没有悬空
#   ④ 每个生效角色真发一次最小请求，并标出该角色是否来自本机文件
#
# 依赖 omp + jq；未安装 omp 时跳过（本仓库在无 omp 时照常可用）。
set -uo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 1

if ! command -v omp >/dev/null 2>&1; then
	echo "跳过 roles-check：本机没有 omp"
	exit 0
fi
if ! command -v jq >/dev/null 2>&1; then
	echo "roles-check 需要 jq" >&2
	exit 1
fi

cfg=".omp/config.yml"
local_file=".omp/settings.json"
example_file=".omp/settings.json.example"
fail=0

# --- 0) 模板卫生 --------------------------------------------------------------
if sed 's/#.*$//' "$cfg" 2>/dev/null | grep -Eq '^[[:space:]]*modelRoles:'; then
	echo "  FAIL  $cfg 里出现了 modelRoles：模板库不写具体模型 id，写这里会盖掉本机 ${local_file}（见文件头说明）"
	fail=1
fi
if [ -f "$local_file" ]; then
	if git ls-files --error-unmatch "$local_file" >/dev/null 2>&1; then
		echo "  FAIL  $local_file 已被 git 跟踪：本机模型表不能进模板库（git rm --cached $local_file 并确认 .gitignore）"
		fail=1
	elif ! git check-ignore -q "$local_file" 2>/dev/null; then
		echo "  FAIL  $local_file 未被 git 忽略：把 .omp/settings.json 加进 .gitignore，否则会连同模型表一起提交"
		fail=1
	fi
fi

settings="$(omp config list --json 2>/dev/null)" || {
	echo "roles-check：读不到 omp 设置（omp config list --json 失败）" >&2
	exit 1
}
roles="$(printf '%s' "$settings" | jq -r '.modelRoles.value // {} | keys[]')"
if [ -z "$roles" ]; then
	echo "roles-check：生效设置里没有 modelRoles —— 本机角色表还没写（${local_file} 或用户层）" >&2
	exit 1
fi

# --- 0b) 本机角色表：必须存在，且覆盖 example 声明的契约角色 --------------------
# 缺了本机表时，生效值会静默来自用户层（多半是编程向模型）——那种"全绿"没有意义，直接拦下。
contract="$(jq -r '.modelRoles // {} | keys[]' "$example_file" 2>/dev/null)"
if [ -z "$contract" ]; then
	echo "roles-check：读不到 ${example_file}（它声明本仓库需要哪些角色）" >&2
	exit 1
fi
if [ ! -f "$local_file" ]; then
	echo "roles-check：缺少本机角色表 ${local_file}" >&2
	echo "  修复：cp ${example_file} ${local_file}，把每个角色填成本机已认证且在订阅计划内的模型，再重跑" >&2
	exit 1
fi
local_keys="$(jq -r '.modelRoles // {} | keys[]' "$local_file" 2>/dev/null)"
for role in $contract; do
	if ! printf '%s\n' "$local_keys" | grep -qx -- "$role"; then
		printf '  FAIL  契约角色 %s 未在 %s 里定义 → 它会静默继承用户层模型（template 与本地表已分叉）\n' "$role" "$local_file"
		fail=1
	fi
done
is_contract() { printf '%s\n' "$contract" | grep -qx -- "$1"; }

# --- 1) @别名悬空引用（无网络） ----------------------------------------------
# frontmatter 里的 model / advisor / prewalk 都可能写 @别名，一并收进来。
refs="$(
	{
		awk 'FNR==1 { dashes=0; in_fm=0 } /^---[[:space:]]*$/ { dashes++; in_fm=(dashes==1); next } in_fm' .omp/agents/*.md 2>/dev/null
		printf '%s' "$settings" | jq -r '.task.value.agentModelOverrides // {} | .[] | select(type=="string")'
	} | grep -o '@[A-Za-z0-9_-]\+' | sort -u
)"
for ref in $refs; do
	name="${ref#@}"
	if ! printf '%s\n' "$roles" | grep -qx -- "$name"; then
		printf '  FAIL  悬空引用 %s：modelRoles 里没有这个角色（现有：%s）\n' "$ref" "$(printf '%s' "$roles" | tr '\n' ' ')"
		fail=1
	fi
done

# --- 2) 逐角色冒烟（真发一次最小请求） ----------------------------------------
# 探针必须在仓库根跑：`--cwd` 换目录会让 omp 找不到本项目 → 读到的是用户层角色表，
# 那样校验的就不是本仓库的配置了。防跑偏靠 `--no-tools`（模型无法读文件）+ 提示词。
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
# 探针本身不引入额外角色请求：关掉 advisor 与 autolearn。
overlay="$tmp/overlay.yml"
cat >"$overlay" <<'YML'
advisor:
  enabled: false
autolearn:
  enabled: false
YML

# 失败信号：非零退出、无输出，或 provider 侧拒绝。
probe_failed() {
	[ -s "$1" ] || return 0
	grep -qE 'exit_code=|MODEL_NOT_IN_PLAN|No API key|permission_error|Unknown model' "$1" && return 0
	return 1
}

probe() {
	local role="$1" log="$tmp/$1.log" attempt
	local args=(omp -p --no-session --no-title --no-tools --config "$overlay" --model "@$role" 'Do not read or write any files. Reply with exactly one token: ROLES_CHECK_OK')
	if command -v timeout >/dev/null 2>&1; then
		args=(timeout 240 "${args[@]}")
	fi
	for attempt in 1 2; do
		"${args[@]}" >"$log" 2>&1 || echo "exit_code=$?" >>"$log"
		probe_failed "$log" || return
		if [ "$attempt" = 1 ]; then
			echo "=== 首次失败，重试一次 ===" >"$log"
			sleep 5
		fi
	done
}

for role in $roles; do probe "$role" & done
wait

# 角色值来自哪一层：本机文件（local）还是用户层/CLI overlay（非 local）。
src_of() {
	if [ -f "$local_file" ]; then
		v="$(jq -r --arg r "$1" '.modelRoles // {} | .[$r] // empty' "$local_file" 2>/dev/null)"
		if [ -n "$v" ]; then
			[ "$v" = "$2" ] && echo local || echo "local 被覆盖"
			return
		fi
	fi
	echo "非 local"
}

echo "角色可用性（每个角色一次最小请求）："
for role in $roles; do
	selector="$(printf '%s' "$settings" | jq -r --arg r "$role" '.modelRoles.value[$r]')"
	origin="$(src_of "$role" "$selector")"
	log="$tmp/$role.log"
	if probe_failed "$log"; then
		printf '  FAIL  %-9s %-46s [%s]\n' "$role" "$selector" "$origin"
		sed 's/^/          /' "$log" | tail -4
		fail=1
	elif is_contract "$role" && [ "$origin" != local ]; then
		printf '  FAIL  %-9s %-46s [%s]  契约角色未由本机 %s 提供（会随用户层漂移）\n' "$role" "$selector" "$origin" "$local_file"
		fail=1
	else
		printf '  ok    %-9s %-46s [%s]\n' "$role" "$selector" "$origin"
	fi
done

if [ "$fail" -ne 0 ]; then
	echo "roles-check 失败：改本机角色表 ${local_file}（或用户层），值必须是「provider 已认证 + 订阅计划内」的模型；见 $cfg 文件头" >&2
	exit 1
fi
printf 'roles-check 通过：%s 个角色全部可用\n' "$(printf '%s\n' "$roles" | wc -l | tr -d ' ')"

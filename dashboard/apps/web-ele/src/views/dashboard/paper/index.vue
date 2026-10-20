<script setup lang="ts">
import EquityChart from './EquityChart.vue';
import { onMounted, onUnmounted, ref } from 'vue';
import { getPaperSummary, getPaperLive, runPaper } from '#/api/paper';
import type { PaperSummary, PaperLiveStatus } from '#/api/paper';

const live = ref<PaperLiveStatus>();
const data = ref<PaperSummary>();
const error = ref('');
const submitting = ref(false);
const account = ref('agent');
const names: Record<string, string> = { linkage: '连板/联动账户', agent: 'Agent 自主账户', rules: '固定规则账户', benchmark: '20% ETF 基准' };
let timer: ReturnType<typeof setTimeout> | undefined;
let stopped = false;
async function refresh() {
  try { const result = await Promise.all([getPaperSummary(), getPaperLive()]); data.value = result[0]; live.value = result[1]; error.value = ''; }
  catch { error.value = '模拟账户加载失败，请检查后端服务'; }
  finally { if (!stopped) timer = setTimeout(refresh, 5000); }
}
async function run() {
  submitting.value = true;
  try { await runPaper(); }
  catch { error.value = '提交失败，请重试'; }
  finally { submitting.value = false; }
}
const actionNames: Record<string, string> = { watch: '观察', buy: '买入', sell: '卖出', hold: '持有' };
const actionName = (action: string) => actionNames[action] || action;
const money = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
onMounted(refresh);
onUnmounted(() => { stopped = true; clearTimeout(timer); });
</script>

<template>
  <div class="paper">
    <div class="heading"><div><h2>Agent 模拟盘</h2><p>收盘后生成计划 · 连板/联动账户盘中每10秒检查行情 · 初始资金10万元</p></div>
      <el-button type="primary" :loading="submitting || data?.status.running" @click="run">运行 / 重试今日决策</el-button>
    </div>
    <el-alert v-if="error || data?.status.error" :title="error || data?.status.error || ''" type="error" :closable="false" />
    <el-alert title="每天16点后生成次日计划。连板/联动账户用实时后续报价估算成交；其余账户仍按日线模拟。电脑需保持唤醒并联网。" type="info" :closable="false" />
    <el-alert v-if="data?.status.message" :title="data.status.message" type="info" :closable="false" />
    <el-card v-if="live" shadow="never" class="live-status">
      <strong>实时模拟执行器：{{ live.heartbeat?.alive ? '运行中' : '未连接' }}</strong>
      <p>行情源：腾讯快照 · {{ live.heartbeat?.session ? '交易时段' : '休市等待' }} · 监控 {{ live.heartbeat?.watching ?? 0 }} 只 · 有效报价 {{ live.heartbeat?.fresh ?? 0 }} 只</p>
      <p>最近心跳：{{ live.heartbeat?.time || '尚未启动' }}</p>
      <el-table :data="live.orders" max-height="220"><el-table-column prop="id" label="实时委托" min-width="260" /><el-table-column prop="state" label="状态" /></el-table>
      <p class="muted">planned 等待触发 · submitted 已提交 · filled 模拟成交 · cancelled 取消 · expired 过期。买卖盘口报价用于成交估算，不模拟排队。</p>
    </el-card>
    <template v-if="data">
      <div class="cards">
        <el-card v-for="(a, key) in data.accounts" :key="key" shadow="never">
          <strong>{{ names[key] }}</strong><h2>¥ {{ money(a.equity) }}</h2>
          <p>收益 {{ a.returnPct }}% · 最大回撤 {{ a.drawdownPct }}%</p><p>可用资金 ¥ {{ money(a.cash) }}</p>
        </el-card>
      </div>
      <el-card shadow="never"><EquityChart :accounts="data.accounts" /></el-card>
      <el-tabs v-model="account">
        <el-tab-pane v-for="(a, key) in data.accounts" :key="key" :name="key" :label="names[key]">
          <h3>持仓</h3>
          <el-table :data="Object.values(a.positions)">
            <el-table-column prop="code" label="代码" /><el-table-column prop="name" label="名称" />
            <el-table-column prop="qty" label="数量" /><el-table-column prop="date" label="买入日期" />
            <el-table-column label="成本"><template #default="{row}">{{ money(row.cost) }}</template></el-table-column>
            <el-table-column prop="mark" label="估值价格" /><el-table-column prop="stop" label="退出参考价" />
            <el-table-column prop="reason" label="持有依据" min-width="220" />
          </el-table>
          <h3>待成交计划</h3>
          <el-table :data="a.orders"><el-table-column prop="date" label="决策日期" /><el-table-column prop="code" label="代码" /><el-table-column label="操作"><template #default="{row}">{{ actionName(row.action) }}</template></el-table-column><el-table-column prop="reason" label="依据" min-width="280" /></el-table>
          <h3>成交与取消记录</h3>
          <el-table :data="[...a.trades].reverse()" max-height="340"><el-table-column prop="filledDate" label="处理日期" /><el-table-column prop="name" label="名称" /><el-table-column label="操作"><template #default="{row}">{{ actionName(row.action) }}</template></el-table-column><el-table-column prop="price" label="模拟价格" /><el-table-column prop="status" label="状态" /><el-table-column prop="note" label="未成交原因" /></el-table>
          <h3>每日净值</h3>
          <el-table :data="[...a.curve].reverse()" max-height="300"><el-table-column prop="date" label="日期" /><el-table-column prop="equity" label="资产（元）" /><el-table-column label="行情未更新持仓"><template #default="{row}">{{ row.stale.join(' / ') || '无' }}</template></el-table-column></el-table>
        </el-tab-pane>
      </el-tabs>
      <el-card shadow="never"><h3>每日决策复盘</h3><el-empty v-if="!data.decisions.length" description="尚无决策，等待当日完整收盘快照" />
        <section v-for="d in data.decisions" :key="d.date"><h4>{{ d.date }} · {{ d.plan.model }}</h4>
          <template v-if="d.linkage"><h4>连板/联动账户 · 次日条件计划</h4><p>{{ d.linkage.error || d.linkage.plan?.review }}</p>
          <el-table :data="d.linkage.plan?.actions || []"><el-table-column prop="code" label="代码" /><el-table-column label="操作"><template #default="{row}">{{ actionName(row.action) }}</template></el-table-column><el-table-column prop="reason" label="A/B联动依据" min-width="280" /></el-table></template><p>{{ d.plan.review }}</p>
          <el-table :data="d.plan.actions"><el-table-column prop="code" label="代码" /><el-table-column label="操作"><template #default="{row}">{{ actionName(row.action) }}</template></el-table-column><el-table-column prop="reason" label="判断依据与退出条件" min-width="300" /></el-table>
        </section>
      </el-card>
      <p class="muted">{{ data.rules }}</p>
    </template>
  </div>
</template>

<style scoped>
.paper { padding: 20px; }
.heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin: 16px 0; }
.muted, .heading p { color: var(--el-text-color-secondary); font-size: 13px; }
</style>

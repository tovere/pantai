<script lang="ts" setup>
type StrategyState = 'conditional' | 'paused' | 'preferred' | 'weak';

interface StrategyRow {
  avgRet: string;
  environment: string;
  name: string;
  rank: number;
  sample: number;
  state: StrategyState;
  totalWin: string;
  type: string;
  verdict: string;
}

const strategies: StrategyRow[] = [
  {
    rank: 1,
    name: '策略5 ETF宽松',
    type: '主线',
    sample: 2935,
    totalWin: '48.7%',
    avgRet: '+0.88%',
    environment: '三种市场状态都能看',
    verdict: '当前最稳，ETF主策略；优先观察A档，仍按结构止损执行',
    state: 'preferred',
  },
  {
    rank: 2,
    name: '策略7 超跌放量回踩二买',
    type: '增强',
    sample: 3813,
    totalWin: '53.3%',
    avgRet: '+1.00%',
    environment: '2024/2025强，2023/2026弱',
    verdict: '总胜率最高；A/C已按回测对调，只做候选增强',
    state: 'weak',
  },
  {
    rank: 3,
    name: '策略10 个股',
    type: '策略5补充',
    sample: 1229,
    totalWin: '46.1%',
    avgRet: '+0.90%',
    environment: '只适合上涨环境',
    verdict: '本质是更严格的三买，和策略5重叠；只看联合A',
    state: 'conditional',
  },
  {
    rank: 4,
    name: '策略5 ETF严格',
    type: '狙击',
    sample: 471,
    totalWin: '48.8%',
    avgRet: '+0.75%',
    environment: '上涨环境更好',
    verdict: '信号少，适合作为ETF宽松版里的加分项',
    state: 'conditional',
  },
  {
    rank: 5,
    name: '策略10 ETF',
    type: '暂停',
    sample: 535,
    totalWin: '44.7%',
    avgRet: '+0.35%',
    environment: '上涨环境才有优势',
    verdict: '和策略5 ETF重叠但更不稳，暂不作为入口',
    state: 'paused',
  },
  {
    rank: 6,
    name: '策略8 个股',
    type: '观察',
    sample: 1080,
    totalWin: '38.3%',
    avgRet: '+0.11%',
    environment: '只在上涨环境观察',
    verdict: '只在上涨环境观察；A仅21笔',
    state: 'weak',
  },
  {
    rank: 7,
    name: '策略5 个股严格',
    type: '观察',
    sample: 3951,
    totalWin: '37.2%',
    avgRet: '接近0',
    environment: '市场状态差异不明显',
    verdict: '没法进入推荐榜；ABC只表示形态完整度',
    state: 'weak',
  },
  {
    rank: 8,
    name: '策略6 个股',
    type: '关闭',
    sample: 4346,
    totalWin: '39.4%',
    avgRet: '-0.16%',
    environment: '三种状态都无优势',
    verdict: '三种状态均无优势，入口已关闭',
    state: 'paused',
  },
  {
    rank: 9,
    name: '策略9 个股',
    type: '关闭',
    sample: 7591,
    totalWin: '37.6%',
    avgRet: '-0.14%',
    environment: '三种状态都偏弱',
    verdict: '三种状态均为负，入口已关闭',
    state: 'paused',
  },
];

const stateLabel = {
  conditional: '条件适用',
  paused: '暂停',
  preferred: '优先',
  weak: '观察',
} as const;

const stateType = {
  conditional: 'warning',
  paused: 'danger',
  preferred: 'success',
  weak: 'info',
} as const;

function getStateLabel(state: StrategyState) {
  return stateLabel[state];
}

function getStateType(state: StrategyState) {
  return stateType[state];
}
</script>

<template>
  <div class="readme-page">
    <header class="page-head">
      <div>
        <h1>策略5-10排名</h1>
        <p>
          2020-2026 独立 AkShare 前复权日线，全量回放；平均收益均为单笔口径。
        </p>
      </div>
      <el-tag type="info" effect="plain">更新于 2026-07-30</el-tag>
    </header>

    <section class="summary-band">
      <div class="summary-main">
        <span class="eyebrow">当前结论</span>
        <strong
          >最有价值的是策略5、策略7、策略10；策略10更像策略5的严格缠论补充。</strong
        >
      </div>
      <div class="summary-rule">
        排名看实盘可用性，不只看胜率；策略7胜率最高，但2023/2026偏弱，所以排第二。
      </div>
    </section>

    <section class="section-block">
      <div class="section-head">
        <div>
          <h2>策略排名</h2>
          <p>排名同时考虑样本量、跨市场状态稳定性和近期样本外表现。</p>
        </div>
      </div>
      <div class="table-wrap">
        <el-table :data="strategies" row-key="name" stripe>
          <el-table-column prop="rank" label="#" width="52" />
          <el-table-column label="策略" min-width="210">
            <template #default="{ row }">
              <div class="strategy-name">
                <span>{{ row.name }}</span>
                <el-tag
                  :type="getStateType(row.state)"
                  size="small"
                  effect="plain"
                >
                  {{ getStateLabel(row.state) }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="type" label="定位" width="100" />
          <el-table-column prop="sample" label="样本" width="88" />
          <el-table-column prop="totalWin" label="总胜率" width="96" />
          <el-table-column prop="avgRet" label="单笔均值" width="108" />
          <el-table-column prop="environment" label="适用环境" min-width="190" />
          <el-table-column prop="verdict" label="结论" min-width="330" />
        </el-table>
      </div>
    </section>

    <section class="section-block methodology">
      <div class="section-head">
        <div>
          <h2>市场状态口径</h2>
          <p>按每笔信号发生当天分类，不按自然年笼统贴牛熊标签。</p>
        </div>
      </div>
      <dl class="regime-grid">
        <div>
          <dt><span class="dot up"></span>上涨</dt>
          <dd>沪深300ETF位于MA60上方、MA20高于MA60，且60日涨幅超过5%。</dd>
        </div>
        <div>
          <dt><span class="dot flat"></span>震荡</dt>
          <dd>不满足明确上涨或下跌条件的市场阶段。</dd>
        </div>
        <div>
          <dt><span class="dot down"></span>下跌</dt>
          <dd>沪深300ETF位于MA60下方、MA20低于MA60，且60日跌幅超过5%。</dd>
        </div>
      </dl>
      <p class="method-note">
        已用0%、3%、5%、8%四组60日收益阈值复核。策略10只在上涨环境有效、策略5
        ETF宽松相对稳定的方向没有改变。
      </p>
    </section>

    <section class="section-block focus-note">
      <div class="section-head">
        <div>
          <h2>为什么策略5个股没有上榜</h2>
          <p>它不是没有样本，而是样本足够后仍没有拉开差异。</p>
        </div>
      </div>
      <div class="focus-grid">
        <div><span>全量样本</span><strong>3951笔</strong></div>
        <div><span>上涨环境</span><strong>+0.07%</strong></div>
        <div><span>震荡环境</span><strong>+0.01%</strong></div>
        <div><span>下跌环境</span><strong>+0.10%</strong></div>
      </div>
      <p>
        三种状态都接近零期望，且滚动年度ABC经常反转。因此策略5个股可以继续提供结构候选，但不能与策略5
        ETF宽松或上涨环境中的策略10个股并列为实盘优先策略。
      </p>
    </section>

    <section class="section-block focus-note">
      <div class="section-head">
        <div>
          <h2>策略7 ABC复测</h2>
          <p>AkShare独立缓存，2020-01-01至2026-07-29，L2止损加涨6%后MA5保护。</p>
        </div>
      </div>
      <div class="focus-grid">
        <div><span>A档</span><strong>1044笔 / 58.2%胜</strong></div>
        <div><span>B档</span><strong>2469笔 / 52.4%胜</strong></div>
        <div><span>C档</span><strong>300笔 / 43.7%胜</strong></div>
        <div><span>总体</span><strong>3813笔 / 53.3%胜</strong></div>
      </div>
      <p>
        当前ABC规则按反弹放量、回踩缩量、L2抬高、止损距离和冲高回落评分；它描述的是形态完整度，
        不是历史收益优先级。复测后原C档胜率最高，因此Dashboard已将策略7的A/C对调：新A表示回测胜率更高，
        但仍需要结合当天市场环境、止损距离和量价确认。
      </p>
    </section>
  </div>
</template>

<style scoped>
.readme-page {
  min-width: 0;
  padding: 20px 24px 40px;
  color: var(--el-text-color-primary);
}
.page-head,
.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}
h1,
h2,
p {
  margin: 0;
}
h1 {
  font-size: 24px;
  line-height: 1.3;
}
h2 {
  font-size: 17px;
  line-height: 1.4;
}
.page-head p,
.section-head p {
  margin-top: 5px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.summary-band {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(260px, 1fr);
  gap: 28px;
  margin: 20px -24px 0;
  padding: 18px 24px;
  border-top: 1px solid var(--el-border-color-light);
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-light);
}
.summary-main {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.summary-main strong {
  font-size: 16px;
  line-height: 1.5;
}
.eyebrow {
  color: var(--el-color-success);
  font-size: 12px;
  font-weight: 600;
}
.summary-rule {
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.65;
}
.section-block {
  padding: 24px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.table-wrap {
  width: 100%;
  margin-top: 14px;
  overflow-x: auto;
}
.table-wrap :deep(.el-table) {
  min-width: 1160px;
}
.strategy-name {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.strategy-name span {
  white-space: nowrap;
}
.regime-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 28px;
  margin: 18px 0 0;
}
.regime-grid > div {
  padding-left: 14px;
  border-left: 1px solid var(--el-border-color);
}
.regime-grid dt {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 600;
}
.regime-grid dd {
  margin: 7px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.65;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dot.up {
  background: var(--el-color-danger);
}
.dot.flat {
  background: var(--el-color-warning);
}
.dot.down {
  background: var(--el-color-success);
}
.method-note,
.focus-note > p {
  margin-top: 18px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.7;
}
.focus-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 1px;
  margin-top: 16px;
  background: var(--el-border-color-lighter);
}
.focus-grid > div {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 14px 16px;
  background: var(--el-bg-color);
}
.focus-grid span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.focus-grid strong {
  font-size: 18px;
}
@media (max-width: 760px) {
  .readme-page {
    padding: 16px 12px 32px;
  }
  .summary-band {
    grid-template-columns: 1fr;
    gap: 12px;
    margin-right: -12px;
    margin-left: -12px;
    padding: 16px 12px;
  }
  .page-head {
    flex-direction: column;
    gap: 10px;
  }
  .regime-grid {
    grid-template-columns: 1fr;
    gap: 14px;
  }
  .focus-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>

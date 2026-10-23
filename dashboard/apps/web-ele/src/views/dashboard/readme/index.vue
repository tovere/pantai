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
    sample: 461,
    totalWin: '52.9%',
    avgRet: '+2.11%',
    environment: '仅上涨市；首中枢+lag≤2+risk≤12%',
    verdict: '样本放宽至461笔；A55.0/B54.1/C43.3，D(非上涨市130笔)36.2%/-1.66%，优于原46.1%/+0.90%',
    state: 'conditional',
  },
  {
    rank: 4,
    name: '策略10 ETF',
    type: 'ETF观察',
    sample: 225,
    totalWin: '63.6%',
    avgRet: '+3.11%',
    environment: '首中枢+回试不破GG；出场移动止损',
    verdict: '与策略5 ETF互补；同板块信号高相关，需去重控仓',
    state: 'conditional',
  },
  {
    rank: 5,
    name: '策略11 VDB回踩',
    type: '条件',
    sample: 703,
    totalWin: '54.1%',
    avgRet: '+2.23%',
    environment: '≥200亿；缩≤0.50+距≤6+ret20≥0+剔反转',
    verdict: '已调优；ABC胜率A55.4/B53.2/C50.7，优于原46.9%/+1.46%',
    state: 'conditional',
  },
  {
    rank: 6,
    name: '策略12 连小阳2档',
    type: '全A主板优先',
    sample: 264,
    totalWin: '71.6%',
    avgRet: '+1.87%',
    environment: '窗涨≤8% + 近20日跌 + 额0.3-1.2亿；放量≥2x跑',
    verdict: '未涨透过滤；小资金优先本档。全量池仅观察',
    state: 'preferred',
  },
  {
    rank: 7,
    name: '策略12 连小阳3档',
    type: '全A主板次选',
    sample: 490,
    totalWin: '70.6%',
    avgRet: '+1.49%',
    environment: '窗涨≤8% + 近20日<5% + 额0.3-1.0亿；放量≥2x跑',
    verdict: '条件略宽于2档，票更多；同样放量离场',
    state: 'conditional',
  },
  {
    rank: 8,
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
    rank: 9,
    name: '策略8 个股',
    type: '关闭',
    sample: 1080,
    totalWin: '38.3%',
    avgRet: '+0.11%',
    environment: '期望接近随机，A仅21笔',
    verdict: '不进主策略，入口已关闭',
    state: 'paused',
  },
  {
    rank: 10,
    name: '策略5 个股严格',
    type: '条件',
    sample: 421,
    totalWin: '49.6%',
    avgRet: '+1.37%',
    environment: '上涨环境 + 距≤6/缩≤0.60/risk≤5',
    verdict: '已调优放宽样本；ABC胜率A58.0/B49.7/C45.4，优于原40.9%/+0.74%',
    state: 'conditional',
  },
  {
    rank: 11,
    name: '策略5 个股宽松',
    type: '条件',
    sample: 959,
    totalWin: '49.4%',
    avgRet: '+1.51%',
    environment: '上涨市；首中枢+距≤5/缩≤0.50/risk≤4/pull≥2',
    verdict: '宽松结构已调优；ABC与严格共用标定A52.2/B46.9/C45.7',
    state: 'conditional',
  },
  {
    rank: 12,
    name: '策略6 个股/ETF',
    type: '关闭',
    sample: 4346,
    totalWin: '39.4%',
    avgRet: '-0.16%',
    environment: '个股三种状态均无优势；ETF未分层验证',
    verdict: '个股与ETF入口均已关闭',
    state: 'paused',
  },
  {
    rank: 13,
    name: '策略9 个股',
    type: '关闭',
    sample: 7591,
    totalWin: '37.6%',
    avgRet: '-0.14%',
    environment: '三种状态都偏弱',
    verdict: '三种状态均为负，入口已关闭',
    state: 'paused',
  },
  {
    rank: 14,
    name: '策略15 昨大涨今缩量回踩',
    type: '新',
    sample: 4108,
    totalWin: '56.4%',
    avgRet: '-0.03%',
    environment: '主板非ST；昨涨停或≥6%；今缩量<0.80x且回踩跌幅≥-3%；尾盘买',
    verdict: '收紧后胜率56.4%。A 69.1%/+0.48%，B贴零，C期望为负仅观察。不进今早可买',
    state: 'weak',
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
          <h2>策略5个股·调优口径</h2>
          <p>严格与宽松均已调优；结构门槛不同，过滤思路一致（贴上沿/缩量/止损近/上涨市）。</p>
        </div>
      </div>
      <div class="focus-grid">
        <div><span>严格调优</span><strong>421笔 / 49.6% / +1.37%</strong></div>
        <div><span>宽松调优</span><strong>959笔 / 49.4% / +1.51%</strong></div>
        <div><span>严格A档</span><strong>58.0% / +2.10%</strong></div>
        <div><span>宽松A档</span><strong>52.2% / +1.97%</strong></div>
      </div>
      <p>
        共用ABC标定：距≤3.5%且缩≤0.45为A，距≤4%为B。ETF主线仍看策略5 ETF宽松。
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

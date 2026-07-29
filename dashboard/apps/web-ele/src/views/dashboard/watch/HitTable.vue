<script lang="ts" setup>
import type { WatchFlag, WatchHit, WatchSection } from '#/api/watch';

import { computed } from 'vue';

import KlineChart from './KlineChart.vue';

const props = defineProps<{ section: WatchSection }>();

type TagType = 'danger' | 'info' | 'primary' | 'success' | 'warning';

const isS5 = computed(() => props.section.strategy === 'chan_wyckoff_3buy');
const isS6 = computed(() => props.section.strategy === 'squeeze_launch');
const isS7 = computed(() => props.section.strategy === 'spring_2buy');
const isS8 = computed(() => props.section.strategy === 'nzi_reversal');
const isS9 = computed(() => props.section.strategy === 'strategy9_distilled');
const isS10 = computed(() => props.section.strategy === 'chan_final');

const GRADE_TYPE: Record<WatchHit['grade'], TagType> = {
  A: 'success',
  B: 'primary',
  C: 'info',
  D: 'danger',
};
const GRADE_LABEL: Record<string, string> = {
  A: 'A 下单级别',
  B: 'B 候选',
  C: 'C 偏弱',
  D: 'D 剔除',
};
const FLAG_TYPE: Record<WatchFlag['type'], TagType> = {
  good: 'success',
  warn: 'warning',
  bad: 'danger',
};

function chgClass(v: number) {
  return v > 0 ? 'up' : v < 0 ? 'down' : '';
}
function fmt(v: number | undefined, digits = 2) {
  return v == null ? '-' : v.toFixed(digits);
}
function sign(v: number | undefined, digits = 1) {
  if (v == null) return '-';
  return `${v > 0 ? '+' : ''}${v.toFixed(digits)}`;
}
function gradeType(grade: WatchHit['grade']): TagType {
  return GRADE_TYPE[grade];
}
function flagType(type: WatchFlag['type']): TagType {
  return FLAG_TYPE[type];
}
</script>

<template>
  <el-empty
    v-if="section.hits.length === 0"
    :description="`今日无命中${section.error ? '（' + section.error + '）' : ''}`"
  />
  <el-table
    v-else
    :data="section.hits"
    row-key="code"
    size="small"
    stripe
    :row-class-name="(o: { row: WatchHit }) => (o.row.grade === 'D' ? 'row-excluded' : '')"
  >
    <el-table-column type="expand">
      <template #default="{ row }">
        <div class="expand-body">
          <div class="expand-note">
            <el-tag :type="gradeType(row.grade)" effect="dark" size="small">
              {{ GRADE_LABEL[row.grade] }}
            </el-tag>
            <span>{{ row.gradeNote }}</span>
          </div>
          <KlineChart :bars="row.bars" :levels="row.levels" />
        </div>
      </template>
    </el-table-column>

    <el-table-column label="代码" width="76" prop="code" />
    <el-table-column label="名称" width="92" prop="name" show-overflow-tooltip />
    <el-table-column label="评级" width="104">
      <template #default="{ row }">
        <el-tag :type="gradeType(row.grade)" effect="dark" size="small">
          {{ GRADE_LABEL[row.grade] }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="现价" width="72" align="right">
      <template #default="{ row }">{{ fmt(row.close) }}</template>
    </el-table-column>
    <el-table-column label="今日%" width="72" align="right">
      <template #default="{ row }">
        <span :class="chgClass(row.chg)">{{ sign(row.chg, 2) }}</span>
      </template>
    </el-table-column>

    <!-- 策略五 列 -->
    <template v-if="isS5">
      <el-table-column label="距上沿" width="72" align="right">
        <template #default="{ row }">{{ sign(row.dist) }}%</template>
      </el-table-column>
      <el-table-column label="中枢#" width="60" align="center">
        <template #default="{ row }">{{ row.stage }}</template>
      </el-table-column>
      <el-table-column label="回踩天" width="66" align="right" prop="pull_days" />
      <el-table-column label="缩量比" width="66" align="right">
        <template #default="{ row }">{{ fmt(row.vol_shrink) }}</template>
      </el-table-column>
      <el-table-column label="三买低" width="72" align="right">
        <template #default="{ row }">{{ fmt(row.buy_low) }}</template>
      </el-table-column>
      <el-table-column label="前涨%" width="66" align="right">
        <template #default="{ row }">{{ sign(row.runup) }}</template>
      </el-table-column>
    </template>

    <!-- 策略六 列 -->
    <template v-else-if="isS6">
      <el-table-column label="压缩分" width="64" align="right" prop="score" />
      <el-table-column label="距MA60" width="72" align="right">
        <template #default="{ row }">{{ sign(row.bias60) }}%</template>
      </el-table-column>
      <el-table-column label="距前高" width="72" align="right">
        <template #default="{ row }">{{ sign(row.dist_high) }}%</template>
      </el-table-column>
      <el-table-column label="前涨%" width="66" align="right">
        <template #default="{ row }">{{ sign(row.runup) }}</template>
      </el-table-column>
      <el-table-column label="蓄势区" width="118" align="center">
        <template #default="{ row }">{{ row.coil }}</template>
      </el-table-column>
      <el-table-column label="止损" width="72" align="right">
        <template #default="{ row }">{{ fmt(row.stop) }}</template>
      </el-table-column>
    </template>

    <!-- 策略七 列 -->
    <template v-else-if="isS7">
      <el-table-column label="背驰%" width="70" align="right">
        <template #default="{ row }">{{ fmt(row.div_pct) }}</template>
      </el-table-column>
      <el-table-column label="离Spring" width="80" align="right">
        <template #default="{ row }">{{ sign(row.up_from_spring) }}%</template>
      </el-table-column>
      <el-table-column label="Spring低" width="80" align="right">
        <template #default="{ row }">{{ fmt(row.spring_low) }}</template>
      </el-table-column>
      <el-table-column label="Spring日" width="72" align="center" prop="spring_date" />
      <el-table-column label="区间下沿" width="80" align="right">
        <template #default="{ row }">{{ fmt(row.range_low) }}</template>
      </el-table-column>
      <el-table-column label="止损" width="72" align="right">
        <template #default="{ row }">{{ fmt(row.stop) }}</template>
      </el-table-column>
    </template>

    <!-- 策略八 列 -->
    <template v-else-if="isS8">
      <el-table-column label="放量倍" width="70" align="right">
        <template #default="{ row }">{{ fmt(row.vexp, 1) }}x</template>
      </el-table-column>
      <el-table-column label="缩量比" width="66" align="right">
        <template #default="{ row }">{{ fmt(row.shrink) }}</template>
      </el-table-column>
      <el-table-column label="回调天" width="66" align="right" prop="pull_days" />
      <el-table-column label="前高" width="72" align="right">
        <template #default="{ row }">{{ fmt(row.peak) }}</template>
      </el-table-column>
      <el-table-column label="回踩低" width="72" align="right">
        <template #default="{ row }">{{ fmt(row.pull_low) }}</template>
      </el-table-column>
      <el-table-column label="前涨%" width="66" align="right">
        <template #default="{ row }">{{ sign(row.runup) }}</template>
      </el-table-column>
      <el-table-column label="止损" width="72" align="right">
        <template #default="{ row }">{{ fmt(row.stop) }}</template>
      </el-table-column>
    </template>

    <!-- 策略九 列 -->
    <template v-else-if="isS9">
      <el-table-column label="入口" width="92" align="center">
        <template #default="{ row }">{{ row.setup || row.kind }}</template>
      </el-table-column>
      <el-table-column label="压缩/背驰" width="92" align="right">
        <template #default="{ row }">
          <span v-if="row.kind === 'coil_launch'">{{ row.score }}分</span>
          <span v-else-if="row.kind === 'spring_2buy'">{{ fmt(row.div_pct) }}%</span>
          <span v-else>{{ row.stage ? `#${row.stage}` : '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="位置" width="96" align="right">
        <template #default="{ row }">
          <span v-if="row.kind === 'coil_launch'">距MA60 {{ sign(row.bias60) }}%</span>
          <span v-else-if="row.kind === 'spring_2buy'">离S {{ sign(row.up_from_spring) }}%</span>
          <span v-else>距上沿 {{ sign(row.dist) }}%</span>
        </template>
      </el-table-column>
      <el-table-column label="止损" width="72" align="right">
        <template #default="{ row }">{{ fmt(row.stop) }}</template>
      </el-table-column>
    </template>

    <!-- 策略十 列(严格笔中枢·缠论三买) -->
    <template v-else-if="isS10">
      <el-table-column label="距ZG" width="72" align="right">
        <template #default="{ row }">{{ sign(row.dist) }}%</template>
      </el-table-column>
      <el-table-column label="中枢#" width="60" align="center">
        <template #default="{ row }">{{ row.stage }}</template>
      </el-table-column>
      <el-table-column label="中枢区间" width="132" align="center">
        <template #default="{ row }">
          {{ fmt(row.zd) }}-{{ fmt(row.zg) }}
        </template>
      </el-table-column>
      <el-table-column label="三买低" width="72" align="right">
        <template #default="{ row }">{{ fmt(row.buy_low) }}</template>
      </el-table-column>
      <el-table-column label="止损" width="72" align="right">
        <template #default="{ row }">{{ fmt(row.stop) }}</template>
      </el-table-column>
      <el-table-column label="风险%" width="70" align="right">
        <template #default="{ row }">-{{ fmt(row.risk, 1) }}%</template>
      </el-table-column>
      <el-table-column label="滞后" width="60" align="right" prop="lag" />
      <el-table-column label="30分共振" width="86" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.sub" type="success" size="small" effect="plain">
            {{ row.sub }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
    </template>

    <el-table-column label="额(亿)" width="72" align="right">
      <template #default="{ row }">{{ fmt(row.amt, 1) }}</template>
    </el-table-column>
    <el-table-column label="盘口标签" min-width="240">
      <template #default="{ row }">
        <el-tag
          v-for="f in row.flags"
          :key="f.text"
          :type="flagType(f.type)"
          size="small"
          class="flag-tag"
          :effect="f.type === 'bad' ? 'dark' : 'plain'"
        >
          {{ f.text }}
        </el-tag>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.up {
  color: #ef4444;
  font-weight: 600;
}
.down {
  color: #22c55e;
  font-weight: 600;
}
.flag-tag {
  margin: 2px 4px 2px 0;
}
.expand-body {
  padding: 8px 16px 16px;
}
.expand-note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
:deep(.row-excluded) {
  opacity: 0.55;
}
</style>

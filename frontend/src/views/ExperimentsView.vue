<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import http, { ApiError } from '../api'
import { useRemote } from '../composables/useRemote'
import type { Algorithm, AlgorithmResult, HistoryUser, Movie, Page } from '../types'
import StatePanel from '../components/StatePanel.vue'
import PageNav from '../components/PageNav.vue'
import AlgorithmPanel from '../components/AlgorithmPanel.vue'

const route = useRoute(), router = useRouter(), auth = useAuth()
const source = ref('ml'), algorithm = ref('content'), selected = ref('')
const userPage = ref(1), users = useRemote<Page<HistoryUser>>(), ratings = useRemote<Page<Movie>>()
const ratingPage = ref(1), available = ref<Algorithm[]>([]), registryError = ref<unknown>(null)
const currentResult = ref<AlgorithmResult | null>(null)

/** S1：RRF 融合面板 */
interface FusionItem { movie_id: string; fusion_rank: number; score: number; recall_sources: string[]; recall_ranks: Record<string, number> }
interface FusionData { sources: string[]; k: number; items: FusionItem[]; leg_summaries: { source: string; count: number }[] }
const fusionData = ref<FusionData | null>(null)
const fusionLoading = ref(false)
const fusionError = ref<unknown>(null)

const fusionEndpoint = computed(() => !subject.value ? null : source.value === 'ml'
  ? `/demo/fusion/${selected.value}/recommendations` : null)  // 注册账号暂不支持 fusion

async function fetchFusion() {
  fusionData.value = null; fusionError.value = null
  if (!fusionEndpoint.value) return
  fusionLoading.value = true
  try {
    const res = await fetch(`/api/v1${fusionEndpoint.value}`, { credentials: 'include' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    fusionData.value = await res.json()
  } catch (e) { fusionError.value = e }
  finally { fusionLoading.value = false }
}
watch(() => fusionEndpoint.value, fetchFusion, { immediate: true })

const algorithmGroups = computed(() => [
  { label: '核心算法 · 学生实现', items: available.value.filter(a => ['content', 'itemcf', 'als'].includes(a.algorithm)) },
  { label: '配套策略 · 热门与冷启动', items: available.value.filter(a => ['popular', 'cold_start'].includes(a.algorithm)) },
])

const evaluationError = ref<unknown>(null), evaluationPending = ref(false), evaluationMissing = ref(false)
/** 离线评价汇总（5 算法在 validation 分区的 Precision@10 / Recall@10） */
interface AlgoMetric { precision_at_10: number; recall_at_10: number; model_version: string; user_count: number }
const metricsSummary = ref<{ algorithms: Record<string, AlgoMetric> } | null>(null)
const metricsLoading = ref(false)

async function fetchMetricsSummary() {
  metricsLoading.value = true
  try {
    const res = await fetch('/evaluation/validation-summary.json', { cache: 'force-cache' })
    if (res.ok) metricsSummary.value = await res.json()
  } catch { /* 指标文件不存在就算了 */ }
  finally { metricsLoading.value = false }
}
void fetchMetricsSummary()
const subject = computed(() => source.value === 'ml' ? (selected.value ? `ml:${selected.value}` : '') : auth.account?.subject_key || '')
const endpoint = computed(() => !subject.value ? null : source.value === 'ml'
  ? `/demo/history-users/${selected.value}/recommendations/${algorithm.value}`
  : `/me/recommendations/${algorithm.value}`)

function updateUrl() { void router.replace({
  path: '/experiments',
  query: { source: source.value, algorithm: algorithm.value, ...(selected.value ? { user: selected.value } : {}) }
}) }

async function fetchUsers(page = userPage.value) {
  userPage.value = page
  await users.load(async () => (await http.get<Page<HistoryUser>>('/demo/history-users',
    { params: { page, per_page: 20 } })).data)
}

function fetchRatings() {
  if (source.value !== 'ml' || !selected.value) return
  return ratings.load(async () => (await http.get<Page<Movie>>(`/demo/history-users/${encodeURIComponent(selected.value)}/ratings`,
    { params: { page: ratingPage.value, per_page: 10 } })).data)
}

async function fetchRegistry() {
  try {
    available.value = (await http.get<{ items: Algorithm[] }>('/experiments/algorithms')).data.items
    registryError.value = null
  } catch (e) { registryError.value = e }
}

async function fetchEvaluation() {
  evaluationPending.value = true; evaluationError.value = null; evaluationMissing.value = false
  try { await http.get('/experiments/evaluations') }
  catch (e) {
    if (e instanceof ApiError && e.status === 501 && e.code === 'EVALUATION_NOT_IMPLEMENTED') evaluationMissing.value = true
    else evaluationError.value = e
  } finally { evaluationPending.value = false }
}

watch(() => route.query, () => {
  source.value = route.query.source === 'app' ? 'app' : 'ml'
  algorithm.value = typeof route.query.algorithm === 'string' && /^[a-z_]+$/.test(route.query.algorithm)
    ? route.query.algorithm : 'content'
  selected.value = typeof route.query.user === 'string' && /^[1-9][0-9]*$/.test(route.query.user)
    ? route.query.user : ''
}, { immediate: true })

watch(() => [selected.value, source.value], () => { ratingPage.value = 1; void fetchRatings() })

void fetchUsers(); void fetchRegistry(); void fetchEvaluation(); void fetchRatings()
</script>

<template>
  <div class="page">
    <div class="page-heading">
      <p class="eyebrow">RECOMMENDATION LAB</p>
      <h1>推荐实验室<span class="heading-dot">.</span></h1>
      <p>从一位观众的历史出发，探索不同算法的推荐结果。</p>
    </div>

    <!-- 更新过的 notice：反映真实接入状态 -->
    <div class="lab-notice notice-success">
      <span class="status-pill status-ok">五种算法已接入</span>
      <p>学生算法（popular / content / itemcf / als / cold_start）已全部就绪。历史用户只读；注册账号与匿名用户相互隔离。</p>
    </div>

    <div class="lab-layout">
      <aside class="lab-controls">
        <h2>实验设置</h2>
        <label for="subject-source">用户来源</label>
        <el-select id="subject-source" v-model="source" @change="updateUrl">
          <el-option label="MovieLens 历史用户（只读）" value="ml" />
          <el-option label="当前注册账号" value="app" />
        </el-select>
        <template v-if="source === 'ml'">
          <label for="history-user">选择历史用户</label>
          <el-select id="history-user" v-model="selected" placeholder="请从真实用户列表选择" @change="updateUrl">
            <el-option v-for="u in users.data.value?.items" :key="u.ml_user_id"
              :label="`${u.subject_key} · ${u.evaluation_role}`" :value="u.ml_user_id" />
          </el-select>
          <StatePanel v-if="users.error.value" :error="users.error.value" @retry="fetchUsers()" />
          <p v-if="users.loading.value" class="muted" role="status">正在加载用户…</p>
          <div class="user-pager">
            <el-button :disabled="userPage === 1 || users.loading.value" @click="fetchUsers(userPage - 1)">上一组</el-button>
            <span>{{ userPage }} / {{ Math.ceil((users.data.value?.total || 0) / 20) || 1 }}</span>
            <el-button :disabled="!users.data.value || userPage * 20 >= users.data.value.total || users.loading.value"
              @click="fetchUsers(userPage + 1)">下一组</el-button>
          </div>
          <p class="form-hint">按原始用户 ID 分页，支持全部课堂历史用户。</p>
        </template>
        <div v-else class="current-subject">
          <p>{{ auth.account?.login_name || '请先登录注册账号' }}</p>
          <span>{{ auth.account?.subject_key || '尚未登录' }}</span>
          <RouterLink v-if="!auth.account" to="/login" class="text-link">前往登录 →</RouterLink>
        </div>

        <label for="algorithm-select">推荐算法</label>
        <el-select id="algorithm-select" v-model="algorithm" @change="updateUrl">
          <el-option-group v-for="group in algorithmGroups" :key="group.label" :label="group.label">
            <el-option v-for="a in group.items" :key="a.algorithm" :label="a.algorithm" :value="a.algorithm" />
          </el-option-group>
        </el-select>

        <div class="algorithm-scope">
          <p><strong>核心算法</strong>内容推荐（基于 genres 的 one-hot + cosine）、ItemCF（item 相似度）、ALS（矩阵分解）。</p>
          <p><strong>配套策略</strong>热门（popularity）、新用户冷启动。</p>
        </div>

        <StatePanel v-if="registryError" :error="registryError" @retry="fetchRegistry()" />

        <!-- 动态 model-info -->
        <div class="model-info">
          <span>当前对象</span>
          <strong>{{ subject || '未选择' }}</strong>
          <span>模型版本</span>
          <strong v-if="currentResult">{{ currentResult.model_version }}</strong>
          <strong v-else class="muted">{{ endpoint ? '加载中…' : '等待选择' }}</strong>
          <span>运行模式</span>
          <strong>business · 只读实验入口</strong>
        </div>
      </aside>

      <div class="lab-results">
        <AlgorithmPanel :label="`${algorithm} · 推荐结果`" :endpoint="endpoint"
          :empty-subject="source === 'ml' ? '请选择历史用户' : '登录后体验'"
          @result-updated="currentResult = $event" />

        <!-- S1: RRF 融合面板 -->
        <section v-if="fusionEndpoint" class="fusion-panel">
          <div class="section-top">
            <h2>RRF 多算法融合</h2>
            <span class="small-label">
              <el-tag size="small" effect="plain">S1</el-tag>
              sources={{ fusionData?.sources?.join(' · ') || '-' }} · k={{ fusionData?.k ?? 60 }}
            </span>
          </div>
          <StatePanel :loading="fusionLoading" :error="fusionError" @retry="fetchFusion">
            <div v-if="fusionData?.items?.length" class="fusion-grid">
              <div v-for="item in fusionData.items" :key="item.movie_id" class="fusion-card">
                <div class="fusion-rank">{{ item.fusion_rank }}</div>
                <div class="fusion-id">#{{ item.movie_id }}</div>
                <div class="fusion-score">score {{ item.score.toFixed(4) }}</div>
                <div class="fusion-sources">
                  <span v-for="s in item.recall_sources" :key="s" class="fusion-source" :title="`rank ${item.recall_ranks[s]}`">
                    {{ s }}<small>#{{ item.recall_ranks[s] }}</small>
                  </span>
                </div>
              </div>
            </div>
          </StatePanel>
        </section>

        <section v-if="source === 'ml'" class="history-panel">
          <div class="section-top"><h2>历史评分</h2><span class="status-pill">{{ subject || '未选择用户' }} · 只读</span></div>
          <StatePanel :loading="ratings.loading.value" :error="ratings.error.value"
            :empty="!selected || !!ratings.data.value && !ratings.data.value.items.length"
            title="选择一位历史观众" description="这里将显示真实历史评分，不提供修改入口。" @retry="fetchRatings">
            <div class="table-scroll">
              <el-table :data="ratings.data.value?.items || []" aria-label="历史用户只读评分表">
                <el-table-column label="电影" min-width="200">
                  <template #default="scope">
                    <RouterLink :to="`/movies/${scope.row.movie_id}`" class="text-link">{{ scope.row.movielens_title }}</RouterLink>
                  </template>
                </el-table-column>
                <el-table-column prop="movie_id" label="电影ID" width="100" />
                <el-table-column prop="rating" label="历史评分" width="100" />
              </el-table>
            </div>
            <PageNav :page="ratingPage" :size="10" :total="ratings.data.value?.total || 0"
              @change="ratingPage = $event; fetchRatings()" />
          </StatePanel>
        </section>

        <section class="evaluation-panel">
          <div class="section-top"><h2>离线评价 · 算法对比</h2><span class="small-label">PRECISION@10 / RECALL@10</span></div>
          <!-- 加载中 -->
          <div v-if="metricsLoading" class="evaluation-empty">
            <span class="status-pill">加载中</span>
            <p>正在读取 validation 分区评价结果…</p>
          </div>
          <!-- 有指标 → 表格 -->
          <div v-else-if="metricsSummary" class="metrics-table-wrap">
            <el-table :data="Object.entries(metricsSummary.algorithms).map(([name, m]) => ({ name, ...m }))"
              aria-label="算法评价对比表" stripe>
              <el-table-column prop="name" label="算法" width="130">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.name === 'itemcf' ? 'primary' : row.name === 'popular' ? 'success' : 'info'" effect="plain">{{ row.name }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="model_version" label="模型版本" width="120" />
              <el-table-column label="Precision@10" width="150">
                <template #default="{ row }">
                  <span class="metric-cell">{{ (row.precision_at_10 * 100).toFixed(2) }}%</span>
                  <div class="metric-bar-bg"><div class="metric-bar-fill" :style="{ width: (row.precision_at_10 * 100 * 2) + '%' }" /></div>
                </template>
              </el-table-column>
              <el-table-column label="Recall@10" width="150">
                <template #default="{ row }">
                  <span class="metric-cell">{{ (row.recall_at_10 * 100).toFixed(2) }}%</span>
                  <div class="metric-bar-bg"><div class="metric-bar-fill recall" :style="{ width: (row.recall_at_10 * 100 * 1.5) + '%' }" /></div>
                </template>
              </el-table-column>
              <el-table-column prop="user_count" label="验证用户数" width="120" />
            </el-table>
            <p class="muted" style="font-size: 12px; margin-top: 10px;">
              数据来源：recommender/student/evaluate.py 离线评价脚本 · validation 分区 · 留出集 rating ≥ 4.0 为正例
            </p>
          </div>
          <!-- 无指标 -->
          <div v-else class="evaluation-empty">
            <span class="status-pill">{{ evaluationMissing ? '尚未实现' : '等待接入' }}</span>
            <p>暂无评价指标，等待离线评价程序接入。</p>
            <small>训练仅允许使用固定 train；此页面不连接 evaluation 数据库。</small>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.algorithm-scope { margin-top: 14px; color: var(--muted); font-size: 12px; line-height: 1.8; }
.algorithm-scope p + p { margin-top: 10px; }
.algorithm-scope strong { display: block; color: var(--text); font-weight: 500; }
.lab-notice.notice-success { background: rgba(64, 158, 255, 0.08); border-left: 3px solid var(--accent); }
.status-pill.status-ok { background: rgba(103, 194, 58, 0.15); color: #67c23a; border-color: #67c23a; }
/* 评价对比表 */
.metrics-table-wrap { padding: 0; }
.metric-cell { font-weight: 600; font-variant-numeric: tabular-nums; color: #e0e7ff; display: inline-block; width: 70px; }
.metric-bar-bg {
  display: inline-block; width: 80px; height: 6px;
  background: rgba(255,255,255,0.08); border-radius: 3px; vertical-align: middle; overflow: hidden; margin-left: 4px;
}
.metric-bar-fill {
  height: 100%; background: linear-gradient(90deg, #6366f1, #3b82f6); border-radius: 3px;
}
.metric-bar-fill.recall {
  background: linear-gradient(90deg, #10b981, #06b6d4);
}
/* S1 RRF 融合面板 */
.fusion-panel { margin-top: 22px; padding: 18px 22px; background: linear-gradient(135deg, rgba(99,102,241,0.06), rgba(59,130,246,0.04)); border: 1px solid rgba(99,102,241,0.25); border-radius: 14px; }
.fusion-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; margin-top: 12px; }
.fusion-card { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 12px; text-align: center; transition: border-color .2s; }
.fusion-card:hover { border-color: rgba(99,102,241,0.5); }
.fusion-rank { font-size: 26px; font-weight: 700; color: #e0e7ff; font-variant-numeric: tabular-nums; }
.fusion-id { color: var(--muted); font-size: 12px; margin: 2px 0; }
.fusion-score { font-size: 11px; color: #a5b4fc; margin-bottom: 8px; }
.fusion-sources { display: flex; flex-wrap: wrap; gap: 4px; justify-content: center; }
.fusion-source { font-size: 10px; padding: 2px 6px; background: rgba(99,102,241,0.15); border-radius: 4px; color: #c7d2fe; }
.fusion-source small { color: #a5b4fc; margin-left: 2px; }
</style>

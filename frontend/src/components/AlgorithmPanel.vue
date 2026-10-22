<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { Connection, InfoFilled, Odometer, ChatDotRound, Document } from '@element-plus/icons-vue'
import http, { ApiError } from '../api'
import StatePanel from './StatePanel.vue'
import MovieCard from './MovieCard.vue'
import type { AlgorithmResult, Movie } from '../types'
import { useAuth } from '../stores/auth'

/** 离线评价指标（Precision@10 / Recall@10） */
interface Metrics {
  algorithm: string
  precision_at_10: number
  recall_at_10: number
  model_version: string
  user_count: number
}
const metrics = ref<Metrics | null>(null)
const metricsLoading = ref(false)

/** explain 弹窗状态 */
interface ExplainState {
  movieId: string
  movieTitle: string
  loading: boolean
  evidence: any | null
  explanation: string
  explanation_mode?: string
  error: string | null
}
const explainState = ref<ExplainState | null>(null)

/** 从 endpoint 解析 { source, subjectId, algorithm } */
function parseSubject(endpoint: string | null, authAccountId: string | null) {
  if (!endpoint) return null
  let m = endpoint.match(/\/demo\/history-users\/(\d+)\/recommendations\/([a-z_]+)/)
  if (m) return { source: 'ml', subjectId: m[1], algorithm: m[2] }
  m = endpoint.match(/\/me\/recommendations\/([a-z_]+)/)
  if (m && authAccountId) return { source: 'app', subjectId: authAccountId, algorithm: m[1] }
  return null
}

/** 支持解释的算法（有真实依据可收集） */
const EXPLAINABLE = new Set(['content', 'itemcf'])

const props = withDefaults(defineProps<{
  endpoint: string | null
  label: string
  emptySubject?: string
  /** 历史用户已评分的电影（含 genres + rating），用于生成推荐原因。可选。 */
  historyRatings?: Movie[]
}>(), { emptySubject: '登录后体验', historyRatings: () => [] })
const emit = defineEmits<{ (e: 'result-updated', result: AlgorithmResult | null): void }>()

/** 本地 movie-details.json 条目（OMDb 下载，离线可用） */
interface LocalMovieDetail {
  director?: string
  actors?: string
  plot?: string
  rated?: string
  runtime?: string
  imdb_rating?: string
  poster_local?: string
  tmdb_poster_path?: string
  imdb_id?: string
  omdb_title?: string
  omdb_year?: string
}
const loading = ref(false), error = ref<unknown>(null), unavailable = ref(false)
const result = ref<AlgorithmResult | null>(null)
const detailsLoading = ref(false)
const movieDetails = ref<Map<string, Movie>>(new Map())
const localDetails = ref<Record<string, LocalMovieDetail>>({})
const localDetailsLoaded = ref(false)
const autoHistoryRatings = ref<Movie[]>([])
let run = 0, detailRun = 0, histRun = 0

async function fetchLocalDetails() {
  if (localDetailsLoaded.value) return
  try {
    const res = await fetch('/movie-details.json', { cache: 'force-cache' })
    if (res.ok) {
      localDetails.value = await res.json()
      localDetailsLoaded.value = true
    }
  } catch { /* 没有就算了，不影响主流程 */ }
}
fetchLocalDetails().catch(() => {})

onScopeDispose(() => { run++; detailRun++; histRun++ })

async function load() {
  const seq = ++run
  error.value = null; result.value = null; unavailable.value = false; loading.value = false
  emit('result-updated', null)
  if (!props.endpoint) return
  loading.value = true
  try {
    const response = await http.get<AlgorithmResult>(props.endpoint)
    if (seq === run) {
      result.value = response.data
      emit('result-updated', response.data)
      void fetchMovieDetails(seq)
    }
  } catch (e) {
    if (seq !== run) return
    if (e instanceof ApiError && e.status === 501 && e.code === 'ALGORITHM_NOT_IMPLEMENTED') {
      unavailable.value = true; emit('result-updated', null)
    }
    else error.value = e
  } finally { if (seq === run) loading.value = false }
}

async function fetchMovieDetails(runSeq: number) {
  const seq = ++detailRun
  detailsLoading.value = true
  const items = result.value?.items || []
  if (!items.length) { detailsLoading.value = false; return }
  const settled = await Promise.allSettled(
    items.map(item => http.get<Movie>(`/movies/${item.movie_id}`))
  )
  if (seq !== detailRun) return
  const map = new Map<string, Movie>()
  settled.forEach((promise, idx) => {
    if (promise.status === 'fulfilled') {
      const movie = promise.value.data
      map.set(items[idx].movie_id, movie)
    }
  })
  movieDetails.value = map
  detailsLoading.value = false
}

watch(() => props.endpoint, load, { immediate: true })

/** 从 endpoint 推断算法名：/demo/.../recommendations/{algo} 或 /me/recommendations/{algo} */
function parseAlgorithm(endpoint: string | null): string | null {
  if (!endpoint) return null
  const m = endpoint.match(/\/recommendations\/([a-z_]+)/)
  return m?.[1] ?? null
}

/** 加载离线评价指标（validation 分区的 Precision@10 / Recall@10） */
async function fetchMetrics(endpoint: string | null) {
  const algo = parseAlgorithm(endpoint)
  metrics.value = null
  if (!algo) return
  metricsLoading.value = true
  try {
    const res = await fetch(`/evaluation/${algo}-validation.json`, { cache: 'force-cache' })
    if (res.ok) {
      metrics.value = await res.json()
    }
  } catch { /* 指标文件不存在就算了 */ }
  finally { metricsLoading.value = false }
}
watch(() => props.endpoint, () => fetchMetrics(props.endpoint), { immediate: true })

/** ====== 推荐解释 ====== */
const auth = useAuth()

async function fetchExplain(movieId: string, movieTitle: string) {
  const subject = parseSubject(props.endpoint, auth.account?.account_id ? String(auth.account.account_id) : null)
  if (!subject) return
  explainState.value = { movieId, movieTitle, loading: true, evidence: null, explanation: '', error: null }
  try {
    const { data } = await http.post('/assistant/explain-recommendation', {
      algorithm: subject.algorithm, movie_id: movieId, source: subject.source, subject_id: subject.subjectId, limit: 10,
    })
    explainState.value = { movieId, movieTitle, loading: false, evidence: data.evidence, explanation: data.explanation || '(无解释)', explanation_mode: data.explanation_mode, error: null }
  } catch (e: any) {
    explainState.value = { movieId, movieTitle, loading: false, evidence: null, explanation: '', error: e?.message || '请求失败' }
  }
}

const currentAlgo = computed(() => parseAlgorithm(props.endpoint))
const canExplain = computed(() => currentAlgo.value && EXPLAINABLE.has(currentAlgo.value))

/** 从 endpoint 推断历史用户 UID；/demo/history-users/{uid}/... → uid，/me/... → null（注册账号） */
function parseHistoryUid(endpoint: string | null): string | null {
  if (!endpoint) return null
  const m = endpoint.match(/^\/demo\/history-users\/([^/]+)\//)
  return m?.[1] ?? null
}

/** 自动拉取历史评分（最多 50 条），为 content 算法 reason 提供 genre 画像。 */
async function autoFetchHistory(endpoint: string | null) {
  const uid = parseHistoryUid(endpoint)
  const seq = ++histRun
  autoHistoryRatings.value = []
  if (!uid) return
  try {
    const r = await http.get<{ items: Movie[] }>(`/demo/history-users/${uid}/ratings`,
      { params: { per_page: 50 } })
    if (seq === histRun) autoHistoryRatings.value = r.data.items
  } catch { /* 拉不到就算了，不影响主流程 */ }
}

// 外部 prop 优先，否则用自动拉的
const effectiveHistoryRatings = computed(() =>
  props.historyRatings.length ? props.historyRatings : autoHistoryRatings.value)

watch(() => props.endpoint, () => autoFetchHistory(props.endpoint), { immediate: true })

const itemsWithDetails = computed(() => {
  if (!result.value) return []
  return result.value.items.map(item => ({
    item,
    movie: movieDetails.value.get(item.movie_id),
  }))
})

/** 算法推荐原因生成。content 算法会结合用户历史高分 genres 输出具体匹配理由。 */
function buildReason(algorithm: string, movieGenres: string[] = [], historyMovies: Movie[] = []): string {
  switch (algorithm) {
    case 'content': {
      // 建 genre → 加权得分（rating - 2.5）映射，正分即用户偏好该 genre
      const genreScores = new Map<string, number>()
      for (const m of historyMovies) {
        const rating = parseFloat(m.rating ?? '0')
        if (!rating) continue
        const weight = rating - 2.5
        for (const g of (m.genres || [])) {
          if (g && g !== '(no genres listed)') {
            genreScores.set(g, (genreScores.get(g) ?? 0) + weight)
          }
        }
      }
      // 历史没有足够 genres → 兜底
      if (genreScores.size === 0) {
        return '基于内容特征推荐（genres one-hot + cosine 余弦相似度）'
      }
      // 找正分 genres 与推荐电影 genres 的交集，按历史打分排序
      const positive = [...genreScores.entries()].filter(([, s]) => s > 0).sort((a, b) => b[1] - a[1])
      const matched: string[] = []
      for (const [g] of positive) {
        if (movieGenres.includes(g) && !matched.includes(g)) matched.push(g)
      }
      if (matched.length) {
        const label = matched.length > 2 ? matched.slice(0, 2).join(' / ') + ` 等 ${matched.length} 类` : matched.join(' / ')
        return `匹配您偏好的「${label}」· 内容相似度推荐`
      }
      return '基于内容特征推荐（genres one-hot + cosine 余弦相似度）'
    }
    case 'itemcf':
      return '物品协同过滤（ItemCF）：推荐与您历史高分电影物品相似的作品'
    case 'als':
      return '矩阵分解（ALS）：隐式反馈下预测您的潜在偏好'
    case 'popular':
      return '热门榜单推荐：该电影在训练集中最受欢迎'
    case 'cold_start':
      return '冷启动策略：基于少量支持集历史 + 热门回退'
    default:
      return '算法推荐'
  }
}

const reasons = computed(() => {
  if (!result.value) return new Map<string, string>()
  const map = new Map<string, string>()
  const alg = result.value.algorithm
  const history = effectiveHistoryRatings.value
  for (const { item, movie } of itemsWithDetails.value) {
    map.set(item.movie_id, buildReason(alg, movie?.genres ?? [], history))
  }
  return map
})
</script>

<template>
  <section class="algorithm-panel" :aria-label="label">
    <div class="section-top">
      <h3>{{ label }}</h3>
      <span class="small-label">RECOMMENDATION LAB</span>
    </div>
    <StatePanel :loading="loading" :error="error" @retry="load">
      <!-- 未选择用户 / 未实现 -->
      <div v-if="!endpoint || unavailable" class="algorithm-empty" role="status">
        <div class="algorithm-symbol"><el-icon aria-hidden="true"><Connection /></el-icon></div>
        <div>
          <span class="status-pill">{{ !endpoint ? emptySubject : '尚未实现' }}</span>
          <h3>{{ !endpoint ? '选择观众，开始探索' : '下一部好电影，等待算法发现' }}</h3>
          <p>{{ !endpoint ? '先选择历史用户或登录注册账号。五种学生算法已全部接入：popular / content / itemcf / als / cold_start。' : '等待算法接入；当前没有模型版本或推荐结果。' }}</p>
        </div>
        <RouterLink v-if="!endpoint && emptySubject === '登录后体验'" class="text-link" to="/login">前往登录 →</RouterLink>
      </div>

      <!-- 有结果 -->
      <div v-else-if="result" class="recommendation-results">
        <header class="results-header">
          <p class="model-meta">
            <el-tag size="small" type="success" effect="plain">{{ result.algorithm }}</el-tag>
            模型 <strong>{{ result.model_version }}</strong>
            · {{ result.dataset_version }}
            · {{ result.items.length }} 条推荐
          </p>
          <!-- 离线评价指标卡片 -->
          <div v-if="metrics || metricsLoading" class="metrics-bar">
            <div v-if="metricsLoading" class="metrics-loading">加载评价指标…</div>
            <template v-else-if="metrics">
              <div class="metric-pill" title="Precision@10：推荐列表前 10 条中有多少是用户真正喜欢的">
                <span class="metric-label">P@10</span>
                <span class="metric-value">{{ (metrics.precision_at_10 * 100).toFixed(2) }}%</span>
              </div>
              <div class="metric-pill" title="Recall@10：用户所有真正喜欢的电影中，有多少被推荐进了前 10">
                <span class="metric-label">R@10</span>
                <span class="metric-value">{{ (metrics.recall_at_10 * 100).toFixed(2) }}%</span>
              </div>
              <span class="metric-sub">基于 validation 分区 · {{ metrics.user_count }} 用户</span>
            </template>
          </div>
          <p v-if="!result.items.length" class="muted">本次没有推荐结果。</p>
        </header>

        <!-- 有电影详情：显示卡片网格 -->
        <div v-if="itemsWithDetails.some(({ movie }) => movie)" class="recommendation-grid">
          <div v-for="{ item, movie } in itemsWithDetails" :key="item.movie_id" class="recommendation-cell">
            <!-- 排名徽章 -->
            <div class="rank-badge" :class="{ 'rank-top': item.rank <= 3 }">#{{ item.rank }}</div>
            <!-- MovieCard 传本地海报 -->
            <MovieCard v-if="movie" :movie="movie"
              :local-path="localDetails[item.movie_id]?.poster_local || null"
              :tmdb-path="localDetails[item.movie_id]?.tmdb_poster_path || null"
              :director="localDetails[item.movie_id]?.director || null"
              :imdb-rating="localDetails[item.movie_id]?.imdb_rating || null"
              :runtime="localDetails[item.movie_id]?.runtime || null"
              :actors="localDetails[item.movie_id]?.actors || null"
            />
            <!-- 详情未加载完 -->
            <div v-else class="movie-card-fallback">
              <div class="poster-fallback">加载中…</div>
              <h3>电影 #{{ item.movie_id }}</h3>
              <p v-if="item.score !== null">模型分数 {{ (item.score * 100).toFixed(1) }}</p>
            </div>
            <!-- 分数徽章 -->
            <div v-if="item.score !== null" class="score-badge" :title="`算法分数 ${item.score}`">
              {{ (item.score * 100).toFixed(0) }}
            </div>
            <!-- 解释按钮（只在 Content/ItemCF 可用） -->
            <div v-if="canExplain" class="explain-row">
              <button class="explain-btn" type="button" @click="fetchExplain(item.movie_id, movie?.movielens_title || `电影#${item.movie_id}`)">
                <el-icon :size="14"><Document /></el-icon> 查看依据
              </button>
              <button class="explain-btn explain-btn-primary" type="button" @click="fetchExplain(item.movie_id, movie?.movielens_title || `电影#${item.movie_id}`)">
                <el-icon :size="14"><ChatDotRound /></el-icon> AI解释
              </button>
            </div>
            <!-- 推荐原因 -->
            <p v-if="!canExplain" class="reason-text" :title="reasons.get(item.movie_id)">
              <el-icon aria-hidden="true"><InfoFilled /></el-icon>
              {{ reasons.get(item.movie_id) }}
            </p>
          </div>
        </div>

        <!-- 详情加载中，但先展示基础信息 -->
        <div v-else class="recommendation-list">
          <ol>
            <li v-for="item in result.items" :key="item.movie_id">
              <RouterLink :to="`/movies/${item.movie_id}`">电影 #{{ item.movie_id }}</RouterLink>
              · 排名 {{ item.rank }}<span v-if="item.score !== null"> · 分数 {{ item.score.toFixed(3) }}</span>
            </li>
          </ol>
        </div>

        <footer v-if="detailsLoading" class="muted small">正在加载电影详情…</footer>
      </div>
    </StatePanel>

    <!-- Explain 弹窗 -->
    <Teleport to="body">
      <transition name="fade">
        <div v-if="explainState" class="explain-overlay" @click.self="explainState = null">
          <div class="explain-modal" role="dialog" aria-modal="true">
            <header class="explain-header">
              <div>
                <h3>#{{ explainState.movieId }} · {{ explainState.movieTitle }}</h3>
                <p class="explain-sub">算法：{{ currentAlgo }} · 用户 {{ parseSubject(props.endpoint, auth.account?.account_id ? String(auth.account.account_id) : null)?.source || '?' }}:{{ parseSubject(props.endpoint, auth.account?.account_id ? String(auth.account.account_id) : null)?.subjectId || '?' }}</p>
              </div>
              <button class="explain-close" type="button" @click="explainState = null" aria-label="关闭">✕</button>
            </header>

            <!-- 加载中 -->
            <div v-if="explainState.loading" class="explain-body">
              <p class="muted">正在分析推荐依据…</p>
            </div>

            <!-- 错误 -->
            <div v-else-if="explainState.error" class="explain-body">
              <p class="muted explain-error">⚠️ {{ explainState.error }}</p>
            </div>

            <!-- 内容 -->
            <div v-else-if="explainState.evidence" class="explain-body">
              <!-- AI 解释（最上面，最重要） -->
              <section class="explain-section explain-ai">
                <h4><el-icon><ChatDotRound /></el-icon> AI 推荐理由</h4>
                <p class="explain-text">{{ explainState.explanation }}</p>
                <p class="muted small">mode: {{ explainState.explanation_mode }}</p>
              </section>

              <!-- 真实依据 -->
              <section class="explain-section">
                <h4><el-icon><Document /></el-icon> 真实推荐依据</h4>
                <template v-if="currentAlgo === 'content'">
                  <div v-if="explainState.evidence.contributing_genres?.length" class="evidence-list">
                    <div class="evidence-title">参与打分的 genres 特征（画像权重 × 候选电影存在）：</div>
                    <div class="evidence-tags">
                      <span v-for="c in explainState.evidence.contributing_genres" :key="c.genre" class="evidence-tag" :class="{ pos: c.profile_weight > 0, neg: c.profile_weight < 0 }">
                        {{ c.genre }} <small>{{ c.profile_weight > 0 ? '+' : '' }}{{ c.profile_weight.toFixed(2) }}</small>
                      </span>
                    </div>
                  </div>
                  <div v-if="explainState.evidence.target_genres?.length" class="evidence-list">
                    <div class="evidence-title">候选电影 genres：</div>
                    <div class="evidence-tags">
                      <span v-for="g in explainState.evidence.target_genres" :key="g" class="evidence-tag neutral">{{ g }}</span>
                    </div>
                  </div>
                  <div v-if="explainState.evidence.user_history_genres_sample?.length" class="evidence-list">
                    <div class="evidence-title">用户历史高分电影样本：</div>
                    <ul class="evidence-items">
                      <li v-for="u in explainState.evidence.user_history_genres_sample" :key="u.movie_id">
                        #{{ u.movie_id }} · {{ u.rating }}分 · {{ u.genres?.join(' / ') }}
                      </li>
                    </ul>
                  </div>
                  <p class="muted small">算法最终得分：{{ explainState.evidence.score?.toFixed(4) }}</p>
                </template>

                <template v-else-if="currentAlgo === 'itemcf'">
                  <div v-if="explainState.evidence.top_contributions?.length" class="evidence-list">
                    <div class="evidence-title">协同配对（种子电影 → 相似度 → 贡献 = sim × rating）：</div>
                    <ul class="evidence-items">
                      <li v-for="(c, i) in explainState.evidence.top_contributions" :key="i">
                        #{{ c.seed_movie_id }}（评分 {{ c.rating }}） · sim={{ c.similarity.toFixed(3) }} · 贡献 {{ c.contribution.toFixed(4) }}
                      </li>
                    </ul>
                  </div>
                  <p class="muted small">算法最终得分：{{ explainState.evidence.score?.toFixed(4) }} · 共使用 {{ explainState.evidence.total_seeds_used }} 部种子电影</p>
                </template>
              </section>

              <p v-if="!explainState.evidence.found" class="muted explain-error">⚠️ {{ explainState.evidence.reason || '证据不足' }}</p>
            </div>
          </div>
        </div>
      </transition>
    </Teleport>
  </section>
</template>

<style scoped>
.results-header { margin-bottom: 16px; }
.model-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; color: var(--text); font-size: 14px; }
.model-meta strong { font-weight: 600; }
/* 离线评价指标 */
.metrics-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-top: 10px; padding: 10px 14px;
  background: linear-gradient(135deg, rgba(99,102,241,0.08), rgba(59,130,246,0.06));
  border: 1px solid rgba(99,102,241,0.2);
  border-radius: 6px;
}
.metrics-loading { font-size: 12px; color: var(--muted); font-style: italic; }
.metric-pill {
  display: inline-flex; align-items: baseline; gap: 6px;
  padding: 4px 12px; border-radius: 16px;
  background: rgba(99,102,241,0.15);
  border: 1px solid rgba(99,102,241,0.3);
}
.metric-label { font-size: 11px; font-weight: 600; color: #a5b4fc; letter-spacing: 0.08em; }
.metric-value { font-size: 16px; font-weight: 700; color: #e0e7ff; font-variant-numeric: tabular-nums; }
.metric-sub { font-size: 11px; color: var(--muted); }
.recommendation-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 18px; }
.recommendation-cell { position: relative; }
.rank-badge {
  position: absolute; top: 10px; left: -4px; z-index: 3;
  background: var(--accent); color: white; font-weight: 700; font-size: 12px;
  padding: 3px 8px; border-radius: 3px; letter-spacing: 0.03em;
  box-shadow: 0 2px 6px rgba(0,0,0,0.25);
}
.rank-badge.rank-top { background: linear-gradient(135deg, #ffd700, #ff8c00); font-size: 14px; padding: 4px 10px; }
.score-badge {
  position: absolute; bottom: 60px; right: 12px; z-index: 3;
  background: rgba(0,0,0,0.75); color: #fff; font-weight: 600; font-size: 13px;
  padding: 3px 8px; border-radius: 10px; backdrop-filter: blur(6px);
}
.movie-card-fallback { text-align: center; padding-top: 8px; }
.poster-fallback { width: 120px; height: 180px; background: var(--muted); margin: 0 auto; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #888; font-size: 12px; }
.recommendation-list ol { padding-left: 18px; line-height: 2.2; }
.small { font-size: 12px; }
.reason-text {
  display: flex; align-items: flex-start; gap: 6px;
  margin: 10px 4px 0;
  padding: 8px 10px;
  font-size: 12px; line-height: 1.5;
  color: #8892a6;
  background: rgba(59, 130, 246, 0.06);
  border-left: 2px solid rgba(59, 130, 246, 0.35);
  border-radius: 2px;
  cursor: default;
}
.reason-text .el-icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--accent, #3b82f6);
  font-size: 13px;
}
/* ====== Explain 按钮 + 弹窗 ====== */
.explain-row {
  display: flex; gap: 6px; margin-top: 6px;
}
.explain-btn {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; font-weight: 500;
  padding: 4px 8px; border-radius: 4px;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15);
  color: #c5d1e2; cursor: pointer; transition: all .15s;
}
.explain-btn:hover { background: rgba(255,255,255,0.12); border-color: var(--accent); color: #fff; }
.explain-btn-primary {
  background: linear-gradient(135deg, rgba(99,102,241,0.35), rgba(59,130,246,0.35));
  border-color: rgba(99,102,241,0.6);
  color: #e0e7ff;
}
.explain-btn-primary:hover { background: linear-gradient(135deg, rgba(99,102,241,0.55), rgba(59,130,246,0.55)); }

.explain-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,0.65); backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.explain-modal {
  background: #1e293b; color: #e2e8f0;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 12px;
  max-width: 640px; width: 100%; max-height: 80vh; overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}
.explain-header {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
  padding: 18px 22px; border-bottom: 1px solid rgba(255,255,255,0.08);
}
.explain-header h3 { margin: 0; font-size: 17px; color: #f1f5f9; }
.explain-sub { margin: 4px 0 0; font-size: 12px; color: #94a3b8; }
.explain-close {
  background: transparent; border: none; color: #94a3b8;
  font-size: 18px; cursor: pointer; padding: 4px 8px; border-radius: 4px;
}
.explain-close:hover { background: rgba(255,255,255,0.1); color: #fff; }
.explain-body { padding: 18px 22px; }
.explain-section { margin-bottom: 18px; }
.explain-section h4 {
  display: flex; align-items: center; gap: 6px;
  margin: 0 0 10px; font-size: 13px; font-weight: 600;
  color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em;
}
.explain-section h4 .el-icon { color: var(--accent); }
.explain-ai {
  background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(59,130,246,0.08));
  border: 1px solid rgba(99,102,241,0.25);
  border-radius: 8px; padding: 14px 16px;
}
.explain-text { font-size: 14px; line-height: 1.7; color: #e2e8f0; margin: 0; }
.explain-error { color: #f87171; }
.evidence-list { margin-bottom: 12px; }
.evidence-title { font-size: 12px; color: #94a3b8; margin-bottom: 6px; }
.evidence-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.evidence-tag {
  padding: 3px 10px; border-radius: 12px; font-size: 12px;
  background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);
}
.evidence-tag.pos { background: rgba(34,197,94,0.15); border-color: rgba(34,197,94,0.3); color: #86efac; }
.evidence-tag.neg { background: rgba(239,68,68,0.15); border-color: rgba(239,68,68,0.3); color: #fca5a5; }
.evidence-tag.neutral { background: rgba(148,163,184,0.15); border-color: rgba(148,163,184,0.25); color: #cbd5e1; }
.evidence-tag small { opacity: 0.8; margin-left: 2px; }
.evidence-items { padding-left: 18px; margin: 0; font-size: 13px; line-height: 1.8; color: #cbd5e1; }
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>

<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { Connection, InfoFilled } from '@element-plus/icons-vue'
import http, { ApiError } from '../api'
import StatePanel from './StatePanel.vue'
import MovieCard from './MovieCard.vue'
import type { AlgorithmResult, Movie } from '../types'

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
            <!-- 推荐原因 -->
            <p class="reason-text" :title="reasons.get(item.movie_id)">
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
  </section>
</template>

<style scoped>
.results-header { margin-bottom: 16px; }
.model-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; color: var(--text); font-size: 14px; }
.model-meta strong { font-weight: 600; }
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
</style>

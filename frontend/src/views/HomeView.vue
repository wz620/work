<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowRight, Search, Reading, Refresh, Switch } from '@element-plus/icons-vue'
import http from '../api'
import { useAuth } from '../stores/auth'
import { useRemote } from '../composables/useRemote'
import type { Movie, Page } from '../types'
import MovieCard from '../components/MovieCard.vue'
import StatePanel from '../components/StatePanel.vue'
import AlgorithmPanel from '../components/AlgorithmPanel.vue'

const route = useRoute()
const auth = useAuth()
const { data, error, loading, load } = useRemote<Page<Movie>>()
const fetchMovies = () => load(async () => (await http.get<Page<Movie>>('/movies', { params: { per_page: 4 } })).data)

// ── 首页推荐：登录用户用个性化算法，未登录用 Popular ──

/** 登录用户可用的个性化算法 */
const PERSONAL_ALGOS = ['content', 'itemcf', 'als'] as const
const ALGO_LABEL: Record<string, string> = {
  content: '基于内容', itemcf: '物品协同', als: '矩阵分解',
  popular: '热门榜单', cold_start: '冷启动',
}

const leftAlgo = ref<string>('als')
const rightAlgo = ref<string>('content')
// 每次刷新给 endpoint 加个 cache-buster，让 AlgorithmPanel.watch(() => props.endpoint) 重新 load
const refreshTick = ref(0)

/** 左侧面板 endpoint */
const leftEndpoint = computed<string | null>(() => {
  const tick = refreshTick.value
  if (!auth.account) return `/public/recommendations/popular?__t=${tick}`
  return `/me/recommendations/${leftAlgo.value}?__t=${tick}`
})
/** 右侧面板 endpoint */
const rightEndpoint = computed<string | null>(() => {
  const tick = refreshTick.value
  if (!auth.account) return `/public/recommendations/popular?__t=${tick}`
  return `/me/recommendations/${rightAlgo.value}?__t=${tick}`
})

function refreshRecommendations() { refreshTick.value++ }

// 登录状态变化 → 重置算法选择 + 自动刷新
watch(() => auth.account?.account_id, () => {
  leftAlgo.value = 'als'; rightAlgo.value = 'content'
  refreshRecommendations()
})

// 路由带 ?refresh=1 时（评分/收藏后回到首页）自动刷新
watch(() => route.query.refresh, v => { if (v === '1') refreshRecommendations() })

onMounted(() => {
  fetchMovies()
  // 详情页评分/收藏后回到首页，自动刷新推荐（让新行为参与计算）
  const flag = localStorage.getItem('reco_refresh')
  if (flag) {
    localStorage.removeItem('reco_refresh')
    setTimeout(refreshRecommendations, 150)
  }
})
</script>
<template>
  <div class="page home-page">
    <section class="hero">
      <div class="hero-copy"><p class="eyebrow"><span /> A MOMENT FOR CINEMA</p><h1>好电影，值得<span>再靠近一点。</span></h1><p class="hero-description">从一部电影开始，发现自己的观影偏好。<br />探索真实片库，让每一次评分留下回响。</p><div class="hero-actions"><RouterLink class="button primary" to="/movies">探索电影库 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink><RouterLink class="button subtle" to="/experiments">进入推荐实验室</RouterLink></div><div class="hero-footnote"><span class="line" /> 浏览 · 记录 · 发现</div></div>
      <div class="hero-art" aria-hidden="true"><div class="orbital orbital-one" /><div class="orbital orbital-two" /><div class="film-ticket"><div class="ticket-top"><span>CINELAB</span><span>ADMIT ONE</span></div><div class="ticket-reel"><span /><span /><span /><span /><i /></div><div class="ticket-caption">THE NEXT<br /><em>discovery.</em></div><div class="ticket-bottom"><span>留一点时间，给电影。</span><span>▶</span></div></div><span class="art-label">YOUR TASTE. YOUR NEXT FILM.</span></div>
    </section>
    <div class="intro-strip"><p><el-icon aria-hidden="true"><Reading /></el-icon><strong>真实片库</strong><span>保留原始 MovieLens 电影标识</span></p><p><el-icon aria-hidden="true"><Search /></el-icon><strong>自由探索</strong><span>按片名与类型发现电影</span></p><RouterLink to="/movies">开始浏览 <span aria-hidden="true">↗</span></RouterLink></div>

    <!-- 推荐区块 -->
    <section class="recommendation-section">
      <div class="section-heading">
        <div>
          <p class="eyebrow">MADE FOR YOUR TASTE</p>
          <h2>你的下一部<span class="heading-dot">.</span></h2>
          <p class="muted">
            <template v-if="auth.account">基于您的历史评分与收藏，{{ auth.account.subject_key }}。</template>
            <template v-else>未登录时展示热门榜单；登录后将启用 ALS / Content / ItemCF 等个性化算法。</template>
          </p>
        </div>
        <div class="reco-actions">
          <!-- 算法切换下拉（登录后才显示） -->
          <template v-if="auth.account">
            <div class="algo-switch">
              <el-select v-model="leftAlgo" size="small" placeholder="左侧算法" @change="refreshRecommendations">
                <el-option v-for="a in PERSONAL_ALGOS" :key="a" :label="ALGO_LABEL[a]" :value="a" />
              </el-select>
              <span class="vs-label">×</span>
              <el-select v-model="rightAlgo" size="small" placeholder="右侧算法" @change="refreshRecommendations">
                <el-option v-for="a in PERSONAL_ALGOS" :key="a" :label="ALGO_LABEL[a]" :value="a" />
              </el-select>
            </div>
          </template>
          <el-button size="small" :icon="Refresh" @click="refreshRecommendations" circle title="重新计算推荐" />
          <RouterLink to="/experiments" class="text-link">实验室 →</RouterLink>
        </div>
      </div>

      <div class="recommendation-columns">
        <AlgorithmPanel :label="auth.account ? `为你推荐 · ${ALGO_LABEL[leftAlgo]}` : '🔥 热门榜单'" :endpoint="leftEndpoint" :empty-subject="'登录后体验更多个性化推荐'" />
        <AlgorithmPanel :label="auth.account ? `相似偏好 · ${ALGO_LABEL[rightAlgo]}` : '🔥 热门榜单'" :endpoint="rightEndpoint" :empty-subject="'登录后体验更多个性化推荐'" />
      </div>

      <!-- 登录 CTA -->
      <div v-if="!auth.account" class="login-cta">
        <p>✨ <b>登录或注册</b>后，你将启用 ALS 矩阵分解、Content 基于内容、ItemCF 物品协同三种真实推荐算法。</p>
        <RouterLink class="button primary" to="/login">登录 / 注册</RouterLink>
      </div>
    </section>

    <section class="browse-section">
      <div class="section-heading">
        <div><p class="eyebrow">THE FILM ARCHIVE</p><h2>从片库出发<span class="heading-dot">.</span></h2><p class="muted">按原始电影编号展示，探索属于你的下一部。</p></div>
        <RouterLink to="/movies" class="text-link">查看全部 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink>
      </div>
      <StatePanel :loading="loading" :error="error" :empty="!!data && !data.items.length" @retry="fetchMovies">
        <div class="movie-grid"><MovieCard v-for="movie in data?.items" :key="movie.movie_id" :movie="movie" /></div>
      </StatePanel>
    </section>
  </div>
</template>

<style scoped>
.hero { min-height: 0; padding: 26px 40px; grid-template-columns: 1.5fr .65fr; align-items: center; }
.hero h1 { font-size: clamp(30px, 2.7vw, 38px); line-height: 1.3; margin: 12px 0; }
.hero .eyebrow { margin-bottom: 8px; }
.hero-description { font-size: 14px; line-height: 1.75; }
.hero-actions { margin-top: 18px; }
.hero-footnote { display: none; }
.hero-art { height: 210px; min-height: 0; transform: none; }
.film-ticket { transform: scale(.62) rotate(9deg); }
.orbital { width: 260px; height: 230px; }
.orbital-two { width: 280px; height: 190px; }
.art-label { display: none; }
.recommendation-section { margin-top: 30px; }

.reco-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.algo-switch { display: flex; align-items: center; gap: 6px; }
.vs-label { color: var(--muted); font-size: 12px; }

.login-cta {
  margin-top: 22px; padding: 16px 22px;
  background: linear-gradient(135deg, rgba(99,102,241,0.1), rgba(59,130,246,0.08));
  border: 1px solid rgba(99,102,241,0.25); border-radius: 10px;
  display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
}
.login-cta p { margin: 0; font-size: 14px; color: var(--text); }

@media (max-width: 780px) {
  .hero { grid-template-columns: 1fr 160px; padding: 24px; gap: 12px; }
  .hero-art { height: 190px; }
  .film-ticket { transform: scale(.52) rotate(9deg); }
}
@media (max-width: 540px) {
  .hero { grid-template-columns: 1fr; padding: 22px 20px; }
  .hero h1 { font-size: 30px; }
  .hero-art { display: none; }
  .hero-actions { gap: 10px; }
  .hero-actions .button { padding: 10px 12px; }
  .recommendation-section { margin-top: 26px; }
}
</style>

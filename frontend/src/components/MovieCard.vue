<script setup lang="ts">
import { computed } from 'vue'
import type { Movie } from '../types'
import MoviePoster from './MoviePoster.vue'
import { getLocalDetail } from '../composables/useLocalDetails'

const props = defineProps<{
  movie: Movie
  /** 本地海报路径（如 /posters/318.jpg）。传了就覆盖 movie-details.json 里的值。 */
  localPath?: string | null
  /** TMDB poster_path（如 /w342/xxx.jpg），走 image.tmdb.org CDN。传了就覆盖。 */
  tmdbPath?: string | null
  director?: string | null
  imdbRating?: string | null
  runtime?: string | null
  actors?: string | null
}>()

// 优先用 prop 传入的值，没有则从全局 movie-details.json 按 movie_id 取。
// 这让 MoviesView / ProfileView / HomeView 的 MovieCard 自动有海报和详情，
// 不必每个页面都手动传 prop。
const local = computed(() => getLocalDetail(props.movie.movie_id))

const effectiveLocalPath = computed(() => props.localPath ?? local.value?.poster_local ?? null)
const effectiveTmdbPath = computed(() => props.tmdbPath ?? local.value?.tmdb_poster_path ?? null)
const effectiveDirector = computed(() => props.director ?? local.value?.director ?? null)
const effectiveImdbRating = computed(() => props.imdbRating ?? local.value?.imdb_rating ?? null)
const effectiveRuntime = computed(() => props.runtime ?? local.value?.runtime ?? null)
const effectiveActors = computed(() => props.actors ?? local.value?.actors ?? null)

const actorsShort = computed(() => {
  if (!effectiveActors.value) return null
  return effectiveActors.value.length > 60 ? effectiveActors.value.slice(0, 58) + '…' : effectiveActors.value
})
</script>
<template>
  <article class="movie-card">
    <RouterLink :to="`/movies/${movie.movie_id}`" :aria-label="`查看 ${movie.title_zh || movie.movielens_title} 详情`">
      <div class="poster-wrap">
        <MoviePoster
          :path="effectiveTmdbPath || movie.poster_path || undefined"
          :local-path="effectiveLocalPath || undefined"
          :title="movie.movielens_title"
        />
        <span class="movie-id">#{{ movie.movie_id }}</span>
        <span v-if="movie.rating" class="my-rating">我的评分 {{ movie.rating }}</span>
        <!-- IMDb 评分徽章（右下角） -->
        <span v-if="effectiveImdbRating" class="imdb-badge" :title="`IMDb ${effectiveImdbRating}/10`">★ {{ effectiveImdbRating }}</span>
      </div>
      <h3>{{ movie.title_zh || movie.movielens_title }}</h3>
      <p class="movie-meta">
        {{ movie.release_year || '年份未收录' }}<span aria-hidden="true"> · </span>
        {{ movie.genres.slice(0, 2).join(' / ') || '类型未收录' }}
        <template v-if="effectiveRuntime"><span aria-hidden="true"> · </span>{{ effectiveRuntime }}</template>
      </p>
      <!-- 导演 -->
      <p v-if="effectiveDirector" class="movie-director" :title="effectiveDirector || undefined">
        <small>导演</small>{{ effectiveDirector }}
      </p>
      <!-- 主演（截取） -->
      <p v-if="actorsShort" class="movie-actors" :title="effectiveActors || undefined">
        {{ actorsShort }}
      </p>
    </RouterLink>
  </article>
</template>

<style scoped>
.movie-meta { font-size: 12px; color: #8892a6; margin: 4px 0 2px; }
.movie-director {
  font-size: 12px; color: #6b7280; margin: 2px 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.movie-director small {
  display: inline-block; font-size: 10px; color: #9ca3af;
  margin-right: 6px; text-transform: uppercase; letter-spacing: 0.04em;
}
.movie-actors {
  font-size: 11px; color: #9ca3af; margin: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.imdb-badge {
  position: absolute; bottom: 6px; right: 6px; z-index: 2;
  background: #f5c518; color: #1a1a1a; font-weight: 700; font-size: 11px;
  padding: 2px 6px; border-radius: 3px;
  line-height: 1;
}
.poster-wrap { position: relative; }
</style>

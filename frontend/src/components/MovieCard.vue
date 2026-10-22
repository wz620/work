<script setup lang="ts">
import { computed } from 'vue'
import type { Movie } from '../types'
import MoviePoster from './MoviePoster.vue'

const props = defineProps<{
  movie: Movie
  /** 本地海报路径（如 /posters/318.jpg） */
  localPath?: string | null
  /** TMDB poster_path（如 /w342/xxx.jpg），走 image.tmdb.org CDN */
  tmdbPath?: string | null
  director?: string | null
  imdbRating?: string | null
  runtime?: string | null
  actors?: string | null
}>()

const actorsShort = computed(() => {
  if (!props.actors) return null
  return props.actors.length > 60 ? props.actors.slice(0, 58) + '…' : props.actors
})
</script>
<template>
  <article class="movie-card">
    <RouterLink :to="`/movies/${movie.movie_id}`" :aria-label="`查看 ${movie.title_zh || movie.movielens_title} 详情`">
      <div class="poster-wrap">
        <MoviePoster :path="tmdbPath || movie.poster_path || undefined" :local-path="localPath || undefined" :title="movie.movielens_title" />
        <span class="movie-id">#{{ movie.movie_id }}</span>
        <span v-if="movie.rating" class="my-rating">我的评分 {{ movie.rating }}</span>
        <!-- IMDb 评分徽章（右下角） -->
        <span v-if="imdbRating" class="imdb-badge" :title="`IMDb ${imdbRating}/10`">★ {{ imdbRating }}</span>
      </div>
      <h3>{{ movie.title_zh || movie.movielens_title }}</h3>
      <p class="movie-meta">
        {{ movie.release_year || '年份未收录' }}<span aria-hidden="true"> · </span>
        {{ movie.genres.slice(0, 2).join(' / ') || '类型未收录' }}
        <template v-if="runtime"><span aria-hidden="true"> · </span>{{ runtime }}</template>
      </p>
      <!-- 导演 -->
      <p v-if="director" class="movie-director" :title="director || undefined">
        <small>导演</small>{{ director }}
      </p>
      <!-- 主演（截取） -->
      <p v-if="actorsShort" class="movie-actors" :title="actors || undefined">
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

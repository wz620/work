/**
 * 全局 movie-details.json 加载器 + 读取器。
 * 在 main.ts 预加载一次后，所有组件通过 inject('localDetails') 或 useLocalDetails() 就能拿到。
 * 这让 MoviesView / ProfileView / HomeView / DetailView 的 MovieCard 也自动显示本地海报和详情，
 * 不必每个调用方都显式传 prop。
 */
import { ref, watchEffect } from 'vue'

export interface LocalMovieDetail {
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

const store = ref<Record<string, LocalMovieDetail>>({})
let loading: Promise<void> | null = null

export function ensureLocalDetails(): Promise<void> {
  if (loading) return loading
  loading = (async () => {
    try {
      const res = await fetch('/movie-details.json', { cache: 'force-cache' })
      if (res.ok) {
        store.value = await res.json()
        console.info(`[localDetails] 加载完成，${Object.keys(store.value).length} 条`)
      }
    } catch (e) {
      console.warn('[localDetails] 加载失败（离线？），降级为空对象', e)
    }
  })()
  return loading
}

/** 组件内调用：按 movie_id 取详情（自动 reactive） */
export function useLocalDetails() {
  return store
}

/**
 * 模板/脚本里直接按 movie_id 取一条。
 * 如果 store 还没加载好，会等 ensureLocalDetails()。
 */
export function getLocalDetail(movieId: string | number): LocalMovieDetail | undefined {
  return store.value[String(movieId)]
}

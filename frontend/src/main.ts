import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './style.css'
import App from './App.vue'
import router from './router'
import { ensureLocalDetails } from './composables/useLocalDetails'

document.documentElement.classList.add('dark')

// 预加载 movie-details.json（包含所有本地海报 + 导演/演员/IMDb 评分等）。
// 在应用启动时异步 fetch 一次，后续所有组件通过 useLocalDetails() 自动拿到，
// 不再需要每个调用点手动把这些字段从 AlgorithmPanel 透传下来。
ensureLocalDetails()

createApp(App).use(createPinia()).use(ElementPlus, { locale: zhCn, size: 'large' }).use(router).mount('#app')

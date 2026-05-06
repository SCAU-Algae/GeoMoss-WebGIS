import './assets/main.css'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { MotionPlugin } from '@vueuse/motion'
import App from './App.vue'
import router from './router'
import { useMessage } from './composables/useMessage'
import { useUserPreferencesStore } from './stores'

const THEME_STORAGE_KEY = 'webgis_color_theme'

function resolveInitialTheme() {
	try {
		const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
		if (stored === 'light' || stored === 'dark') return stored
		return 'dark'
	} catch {
		return 'dark'
	}
}

if (typeof document !== 'undefined') {
	document.documentElement.dataset.theme = resolveInitialTheme()
}

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(MotionPlugin)

const userPreferencesStore = useUserPreferencesStore(pinia)
void userPreferencesStore.bootstrap()

// Mount immediately so RouterView and GlobalLoading can render during async guards.
app.mount('#app')

// Keep message host initialization after router ready.
router.isReady().finally(() => {
	queueMicrotask(() => {
		const message = useMessage()
		message.ensureMessageHost('top-center')
	})
})

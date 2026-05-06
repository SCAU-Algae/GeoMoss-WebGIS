<template>
    <div class="register-container">
        <div class="container fade-in">
            <div class="form-header">
                <h1 class="form-title">GeoMoss</h1>
                <h1 class="form-title"> 用户登录/注册</h1>
                <p class="form-subtitle">登录以访问系统主页与受保护 API</p>

                <div class="quick-hints">
                    <div class="hint-item">游客登陆API受限</div>
                </div>
            </div>
            
            <div class="form-body">
                <div class="mode-switch" role="tablist" aria-label="登录或注册">
                    <button type="button" class="mode-btn" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
                    <button type="button" class="mode-btn" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
                </div>

                <form @submit.prevent="handleSubmit">
                    <!-- 登录模式：用户名 + 密码 -->
                    <template v-if="mode === 'login'">
                        <div class="form-group">
                            <label for="username">用户名</label>
                            <div class="input-group">
                                <i class="icon fas fa-user"></i>
                                <input type="text" id="username" v-model="username" placeholder="请输入用户名（游客请输入 user）" @blur="handleUsernameBlur" />
                            </div>
                            <div class="hint">登录角色由后端统一校验（游客/注册用户/管理员）</div>
                        </div>
                        <div class="form-group">
                            <label for="password">密码</label>
                            <div class="input-group">
                                <i class="icon fas fa-lock"></i>
                                <input type="password" id="password" v-model="password" placeholder="请输入密码" required />
                            </div>
                            <div class="hint">游客默认一键登陆，无需密码</div>
                        </div>
                    </template>

                    <!-- 注册模式：邮箱 → CAPTCHA → 验证码 → 设置用户名密码 -->
                    <template v-if="mode === 'register'">
                        <div class="form-group">
                            <label for="reg-email">邮箱地址</label>
                            <div class="input-group">
                                <i class="icon fas fa-envelope"></i>
                                <input id="reg-email" v-model="emailInput" type="email" placeholder="your@email.com" required autocomplete="email" />
                            </div>
                        </div>
                        <!-- CAPTCHA -->
                        <div v-if="emailStep !== 'code'" class="form-group">
                            <label>人机验证</label>
                            <div class="captcha-row">
                                <img v-if="captchaImage" :src="captchaImage" class="captcha-img" @click="refreshCaptcha" title="点击刷新" alt="验证码" />
                                <span v-else class="captcha-text-fallback">{{ captchaText }}</span>
                                <button type="button" class="captcha-refresh" @click="refreshCaptcha" title="换一张">↻</button>
                            </div>
                            <div class="input-group" style="margin-top:8px">
                                <i class="icon fas fa-shield-alt"></i>
                                <input v-model="captchaInput" type="text" maxlength="4" placeholder="输入图中字符" autocomplete="off" />
                            </div>
                        </div>
                        <!-- Email verification code (after sending) -->
                        <template v-if="emailStep === 'code'">
                            <div class="form-group">
                                <label for="reg-code">邮箱验证码</label>
                                <div class="input-group">
                                    <i class="icon fas fa-key"></i>
                                    <input id="reg-code" v-model="emailCodeInput" type="text" maxlength="6" placeholder="6 位数字验证码" autocomplete="off" />
                                </div>
                                <div class="hint">验证码已发送至 {{ emailInput }}，10 分钟内有效</div>
                            </div>
                            <div class="form-group">
                                <label for="reg-user">用户名</label>
                                <div class="input-group">
                                    <i class="icon fas fa-user"></i>
                                    <input id="reg-user" v-model="emailUsername" type="text" placeholder="3-24位：字母/数字/下划线" autocomplete="off" />
                                </div>
                            </div>
                            <div class="form-group">
                                <label for="reg-pass">密码</label>
                                <div class="input-group">
                                    <i class="icon fas fa-lock"></i>
                                    <input id="reg-pass" v-model="emailPassword" type="password" placeholder="6-64位，至少含字母和数字" autocomplete="new-password" />
                                </div>
                            </div>
                        </template>
                        <div v-if="emailMessage" :class="['validation-message', emailStatus]">{{ emailMessage }}</div>
                        <button type="button" class="btn" :disabled="emailSending" @click="handleEmailAction">
                            {{ emailSending ? '处理中...' : (emailStep === 'code' ? '完成注册' : '发送验证码') }}
                        </button>
                    </template>

                    <div class="quick-action-row" v-if="mode === 'login'">
                        <button type="button" class="quick-btn guest-login" @click="quickGuestLogin">
                            <i class="fas fa-person-hiking"></i>
                            游客一键登陆
                        </button>
                        <button type="button" class="quick-btn confirm-login" :disabled="isSubmitting" @click="handleSubmit">
                            <i class="fas fa-sign-in-alt"></i>
                            {{ isSubmitting ? '处理中...' : '确认登陆' }}
                        </button>
                    </div>

                    <div v-if="formMessage" :class="['validation-message', formStatus]">
                        {{ formMessage }}
                    </div>
                    
                    <div class="login-link">
                        <template v-if="mode === 'login'">
                            还没有账号？ <a href="#" @click.prevent="switchMode('register')">立即注册</a>
                            <span class="link-divider">|</span>
                            <a href="#" @click.prevent="mode = 'forgot'">忘记密码</a>
                        </template>
                        <template v-else>
                            已有账号？ <a href="#" @click.prevent="mode = 'login'; emailStep = 'send'">返回登录</a>
                        </template>
                    </div>

                    <!-- 忘记密码 -->
                    <template v-if="mode === 'forgot'">
                        <div class="form-group">
                            <label for="forgot-user">用户名</label>
                            <div class="input-group">
                                <i class="icon fas fa-user"></i>
                                <input id="forgot-user" v-model="forgotUsername" type="text" placeholder="输入已绑定邮箱的账号" />
                            </div>
                        </div>
                        <template v-if="forgotStep === 'code'">
                            <div class="form-group">
                                <label for="forgot-code">验证码</label>
                                <div class="input-group">
                                    <i class="icon fas fa-key"></i>
                                    <input id="forgot-code" v-model="forgotCodeInput" type="text" maxlength="6" placeholder="6 位数字验证码" />
                                </div>
                                <div class="hint">验证码已发送至绑定邮箱</div>
                            </div>
                            <div class="form-group">
                                <label for="forgot-pass">新密码</label>
                                <div class="input-group">
                                    <i class="icon fas fa-lock"></i>
                                    <input id="forgot-pass" v-model="forgotNewPassword" type="password" placeholder="6-64位，至少含字母和数字" />
                                </div>
                            </div>
                        </template>
                        <div v-if="forgotMessage" :class="['validation-message', forgotStatus]">{{ forgotMessage }}</div>
                        <button type="button" class="btn" :disabled="forgotLoading" @click="handleForgotAction">
                            {{ forgotLoading ? '处理中...' : (forgotStep === 'code' ? '重置密码' : '发送验证码') }}
                        </button>
                    </template>
                </form>
            </div>
            
            <div class="form-footer">
                登录即表示您同意我们的 <a href="#">服务条款</a> 和 <a href="#">隐私政策</a>
            </div>
        </div>
    </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useMessage } from '../composables/useMessage';
import { apiAuthCheckUsername, apiAuthLogin, apiAuthRegister, apiLocationTrackVisit, syncUserRoleToUrl } from '../api/backend';
import {
    consumePersistedPositionCode,
    getAuthToken,
    getOrCreateGuestDeviceId,
    injectPositionCodeToPath,
    peekPersistedPositionCode,
    setAuthSession,
} from '../utils/auth';

const router = useRouter();
const route = useRoute();
const message = useMessage();

const mode = ref('login');
const username = ref('');
const password = ref('');
const confirmPassword = ref('');
const selectedAvatarIndex = ref(0);
const isSubmitting = ref(false);
const isCheckingUsername = ref(false);
const formMessage = ref('');
const emailStep = ref('send');
const emailInput = ref('');
const emailUsername = ref('');
const emailPassword = ref('');
const emailCodeInput = ref('');
const emailSending = ref(false);
const emailMessage = ref('');
const emailStatus = ref('');
const captchaImage = ref('');
const captchaId = ref('');
const captchaText = ref('');
const captchaInput = ref('');

// ── Forgot Password ──
const forgotUsername = ref('');
const forgotStep = ref('send');
const forgotCodeInput = ref('');
const forgotNewPassword = ref('');
const forgotLoading = ref(false);
const forgotMessage = ref('');
const forgotStatus = ref('');
const formStatus = ref('');
const usernameCheckStatus = ref('');
const usernameCheckMessage = ref('');
const lastCheckedUsername = ref('');
let gisPrewarmTimer = null;

const usernameRegex = /^[A-Za-z0-9_]{3,24}$/;
const passwordRegex = /^(?=.*[A-Za-z])(?=.*\d).{6,64}$/;
const reservedNames = new Set(['user', 'admin']);

const avatarOptions = computed(() => {
    return Array.from({ length: 12 }, (_, index) => ({
        index,
        label: `头像 ${index + 1}`,
        src: resolvePublicAssetPath(`avatars/avatar-${index}.svg`)
    }));
});

const usernameCheckIcon = computed(() => {
    if (usernameCheckStatus.value === 'success') {
        return 'fas fa-check-circle';
    }
    if (usernameCheckStatus.value === 'loading') {
        return 'fas fa-spinner fa-spin';
    }
    return 'fas fa-exclamation-circle';
});

function setFormState(status = '', text = '') {
    formStatus.value = status;
    formMessage.value = text;
}

function normalizeUsername(raw) {
    return String(raw || '').trim();
}

function resolvePublicAssetPath(relativePath) {
    const base = String(import.meta.env.BASE_URL || '/').trim();
    const normalizedBase = base.endsWith('/') ? base : `${base}/`;
    const normalizedPath = String(relativePath || '').replace(/^\/+/, '');
    return `${normalizedBase}${normalizedPath}`;
}

function resetUsernameCheck() {
    usernameCheckStatus.value = '';
    usernameCheckMessage.value = '';
    lastCheckedUsername.value = '';
}

function resolveRedirectTarget() {
    const redirect = String(route.query?.redirect || '/home').trim();
    const safeRedirect = redirect.startsWith('/') ? redirect : '/home';
    const persistedPositionCode = peekPersistedPositionCode();
    return injectPositionCodeToPath(safeRedirect, persistedPositionCode);
}

function switchMode(nextMode) {
    mode.value = nextMode;
    setFormState('', '');
    if (nextMode === 'login') {
        confirmPassword.value = '';
        resetUsernameCheck();
        selectedAvatarIndex.value = 0;
    }
    if (nextMode === 'register') {
        emailStep.value = 'send';
        emailMessage.value = '';
        emailCodeInput.value = '';
        refreshCaptcha();
    }
}

function fillGuestAccount() {
    mode.value = 'login';
    username.value = 'user';
    password.value = '123';
    resetUsernameCheck();
    setFormState('success', '已填入游客账号，请点击“登录系统”');
}
async function quickGuestLogin() {
    isSubmitting.value = true;
    setFormState('', '');

    try {
        const guestDeviceId = getOrCreateGuestDeviceId();
        // 游客一键登陆：账号 user，密码 123
        const result = await apiAuthLogin({ 
            username: 'user',
            password: '123',
            guest_device_id: guestDeviceId || undefined,
        });
        const token = String(result?.token || '').trim();
        const user = result?.user || null;

        if (!token || !user) {
            throw new Error('游客登录响应异常，请稍后重试');
        }

        setAuthSession({ token, user });
        syncUserRoleToUrl(user);
        message.success(`游客登陆成功，欢迎使用！`);
        await router.replace(resolveRedirectTarget());
        consumePersistedPositionCode();
    } catch (error) {
        const detail = String(
            error?.originalError?.response?.data?.detail
            || error?.message
            || '游客登陆失败，请稍后重试'
        );
        setFormState('error', detail);
        message.error(detail);
    } finally {
        isSubmitting.value = false;
    }
}
async function checkUsernameAvailability({ silent = false, force = false } = {}) {
    if (mode.value !== 'register') {
        return true;
    }

    const normalizedUsername = normalizeUsername(username.value);
    if (!normalizedUsername) {
        usernameCheckStatus.value = 'error';
        usernameCheckMessage.value = '请先输入用户名';
        lastCheckedUsername.value = '';
        if (!silent) {
            message.warning(usernameCheckMessage.value);
        }
        return false;
    }

    const lowered = normalizedUsername.toLowerCase();
    if (reservedNames.has(lowered)) {
        usernameCheckStatus.value = 'error';
        usernameCheckMessage.value = 'user/admin 为系统保留用户名';
        lastCheckedUsername.value = normalizedUsername;
        if (!silent) {
            message.warning(usernameCheckMessage.value);
        }
        return false;
    }

    if (!usernameRegex.test(normalizedUsername)) {
        usernameCheckStatus.value = 'error';
        usernameCheckMessage.value = '用户名仅支持字母、数字、下划线，长度 3-24 位';
        lastCheckedUsername.value = normalizedUsername;
        if (!silent) {
            message.warning(usernameCheckMessage.value);
        }
        return false;
    }

    if (
        !force
        && normalizedUsername === lastCheckedUsername.value
        && (usernameCheckStatus.value === 'success' || usernameCheckStatus.value === 'error')
    ) {
        return usernameCheckStatus.value === 'success';
    }

    isCheckingUsername.value = true;
    usernameCheckStatus.value = 'loading';
    usernameCheckMessage.value = '正在检查用户名可用性...';

    try {
        const result = await apiAuthCheckUsername(normalizedUsername);
        const available = Boolean(result?.available);
        const detail = String(result?.message || (available ? '用户名可用' : '用户名不可用'));

        lastCheckedUsername.value = normalizedUsername;
        usernameCheckStatus.value = available ? 'success' : 'error';
        usernameCheckMessage.value = detail;

        if (!silent && !available) {
            message.warning(detail);
        }

        return available;
    } catch (error) {
        const detail = String(
            error?.originalError?.response?.data?.detail
            || error?.message
            || '用户名校验失败，请稍后重试'
        );
        usernameCheckStatus.value = 'error';
        usernameCheckMessage.value = detail;
        lastCheckedUsername.value = normalizedUsername;
        if (!silent) {
            message.error(detail);
        }
        return false;
    } finally {
        isCheckingUsername.value = false;
    }
}

async function handleUsernameBlur() {
    if (mode.value !== 'register') {
        return;
    }
    await checkUsernameAvailability();
}

async function handleLogin() {
    const normalizedUsername = normalizeUsername(username.value);
    const normalizedPassword = String(password.value || '').trim();

    if (!normalizedPassword) {
        setFormState('error', '请输入密码');
        return;
    }

    isSubmitting.value = true;
    setFormState('', '');

    try {
        const payload = { password: normalizedPassword };
        if (normalizedUsername) {
            payload.username = normalizedUsername;
        }
        if (normalizedUsername.toLowerCase() === 'user') {
            payload.guest_device_id = getOrCreateGuestDeviceId() || undefined;
        }

        const result = await apiAuthLogin(payload);
        const token = String(result?.token || '').trim();
        const user = result?.user || null;

        if (!token || !user) {
            throw new Error('登录响应异常，请稍后重试');
        }

        setAuthSession({ token, user });
        syncUserRoleToUrl(user);
        message.success(`登录成功，当前角色：${String(user.role || 'unknown')}`);
        await router.replace(resolveRedirectTarget());
        consumePersistedPositionCode();
    } catch (error) {
        const detail = String(
            error?.originalError?.response?.data?.detail
            || error?.message
            || '登录失败，请稍后重试'
        );
        setFormState('error', detail);
        message.error(detail);
    } finally {
        isSubmitting.value = false;
    }
}

async function handleRegister() {
    const normalizedUsername = normalizeUsername(username.value);
    const normalizedPassword = String(password.value || '').trim();
    const normalizedConfirmPassword = String(confirmPassword.value || '').trim();

    if (!normalizedUsername) {
        setFormState('error', '请填写用户名');
        return;
    }

    if (reservedNames.has(normalizedUsername.toLowerCase())) {
        setFormState('error', 'user/admin 为系统保留用户名');
        return;
    }

    if (!usernameRegex.test(normalizedUsername)) {
        setFormState('error', '用户名仅支持字母、数字、下划线，长度 3-24 位');
        return;
    }

    if (!passwordRegex.test(normalizedPassword)) {
        setFormState('error', '密码需包含字母和数字，长度 6-64 位');
        return;
    }

    if (normalizedConfirmPassword !== normalizedPassword) {
        setFormState('error', '两次输入的密码不一致');
        return;
    }

    const isUsernameAvailable = await checkUsernameAvailability({ silent: true, force: true });
    if (!isUsernameAvailable) {
        const detail = usernameCheckMessage.value || '用户名不可用，请更换后重试';
        setFormState('error', detail);
        message.warning(detail);
        return;
    }

    isSubmitting.value = true;
    setFormState('', '');

    try {
        await apiAuthRegister(
            normalizedUsername,
            normalizedPassword,
            selectedAvatarIndex.value,
        );
        message.success('注册成功，请使用新账号登录');
        password.value = '';
        confirmPassword.value = '';
        selectedAvatarIndex.value = 0;
        resetUsernameCheck();
        switchMode('login');
        setFormState('success', '注册完成，请输入账号密码登录');
    } catch (error) {
        const detail = String(
            error?.originalError?.response?.data?.detail
            || error?.message
            || '注册失败，请稍后重试'
        );
        setFormState('error', detail);
        message.error(detail);
    } finally {
        isSubmitting.value = false;
    }
}

async function refreshCaptcha() {
    try {
        const resp = await fetch('/api/auth/email/captcha');
        const ct = resp.headers.get('content-type') || '';
        if (ct.includes('image')) {
            const blob = await resp.blob();
            captchaImage.value = URL.createObjectURL(blob);
            captchaId.value = resp.headers.get('X-Captcha-Id') || '';
            captchaText.value = '';
        } else {
            const json = await resp.json();
            captchaImage.value = '';
            captchaId.value = json.captcha_id;
            captchaText.value = json.captcha_text;
        }
    } catch { /* ignore */ }
}

async function handleEmailAction() {
    emailMessage.value = '';
    emailSending.value = true;
    try {
        if (emailStep.value === 'send') {
            const resp = await fetch('/api/auth/email/send-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: emailInput.value.trim(),
                    captcha_id: captchaId.value,
                    captcha_text: captchaInput.value,
                }),
            });
            const json = await resp.json();
            if (!resp.ok) throw new Error(json.detail || '发送失败');
            emailStep.value = 'code';
            emailStatus.value = 'success';
            emailMessage.value = json.message;
            refreshCaptcha();
        } else {
            const resp = await fetch('/api/auth/email/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: emailInput.value.trim(),
                    code: emailCodeInput.value.trim(),
                    username: emailUsername.value.trim(),
                    password: emailPassword.value,
                    avatar_index: selectedAvatarIndex.value ?? 0,
                }),
            });
            const json = await resp.json();
            if (!resp.ok) throw new Error(json.detail || '验证失败');
            emailStatus.value = 'success';
            emailMessage.value = json.message + '，请切换到登录页面登录';
            setTimeout(() => {
                emailInput.value = '';
                emailUsername.value = '';
                emailPassword.value = '';
                emailCodeInput.value = '';
                captchaInput.value = '';
                emailStep.value = 'send';
                switchMode('login');
            }, 2000);
        }
    } catch (e) {
        emailStatus.value = 'error';
        emailMessage.value = e.message;
        refreshCaptcha();
    } finally {
        emailSending.value = false;
    }
}

async function handleForgotAction() {
    forgotMessage.value = '';
    forgotLoading.value = true;
    try {
        if (forgotStep.value === 'send') {
            const resp = await fetch('/api/auth/email/forgot-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: forgotUsername.value.trim() }),
            });
            const json = await resp.json();
            if (!resp.ok) throw new Error(json.detail || '发送失败');
            forgotStep.value = 'code';
            forgotStatus.value = 'success';
            forgotMessage.value = json.message;
        } else {
            const resp = await fetch('/api/auth/email/reset-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: forgotUsername.value.trim(),
                    code: forgotCodeInput.value.trim(),
                    new_password: forgotNewPassword.value,
                }),
            });
            const json = await resp.json();
            if (!resp.ok) throw new Error(json.detail || '重置失败');
            forgotStatus.value = 'success';
            forgotMessage.value = json.message;
            setTimeout(() => {
                mode.value = 'login';
                forgotStep.value = 'send';
                forgotMessage.value = '';
            }, 2000);
        }
    } catch (e) {
        forgotStatus.value = 'error';
        forgotMessage.value = e.message;
    } finally {
        forgotLoading.value = false;
    }
}

async function handleSubmit() {
    if (isSubmitting.value) return;
    if (mode.value === 'register') {
        await handleRegister();
        return;
    }
    await handleLogin();
}

onMounted(async () => {
    const token = getAuthToken();
    if (token) {
        await router.replace(resolveRedirectTarget());
        consumePersistedPositionCode();
        return;
    }

    // 自动发送定位追踪请求（无需等待，异步处理）
    // 用户进入登陆页面时自动记录访问信息到数据库
    apiLocationTrackVisit({
        userAgent: navigator?.userAgent,
        referrer: document?.referrer
    }).then((result) => {
        if (result?.tracked) {
            console.log('[Location Tracking] 访问已记录:', {
                ip: result?.ip,
                city: result?.city,
                province: result?.province,
                country: result?.country
            });
        }
    }).catch((error) => {
        // 失败不影响登陆页面使用，静默处理
        console.warn('[Location Tracking] 追踪请求失败:', error?.message);
    });
    // 首屏加载后默认1秒 1S 1s 后开始加载，可根据实际情况调整这个预热时机和延迟，确保不与首屏关键资源争抢带宽。 
    // 登录页就绪 1 秒后才开始后台预热 GIS 资产，避免首屏带宽争抢。
    if (typeof window !== 'undefined') {
        gisPrewarmTimer = window.setTimeout(() => {
            if (route.name !== 'register') return;

            import('../utils/gis/deferredGisWarmupLauncher')
                .then((mod) => mod.launchDeferredGisWarmup())
                .catch((error) => {
                    console.warn('[GIS Prewarm] 预热失败(不影响登录流程):', error?.message || error);
                });
        }, 1000);
    }
});

onUnmounted(() => {
    if (gisPrewarmTimer !== null && typeof window !== 'undefined') {
        window.clearTimeout(gisPrewarmTimer);
        gisPrewarmTimer = null;
    }
});

watch(username, (nextUsername) => {
    if (mode.value !== 'register') {
        return;
    }

    const normalized = normalizeUsername(nextUsername);
    if (!normalized) {
        resetUsernameCheck();
        return;
    }

    if (normalized !== lastCheckedUsername.value) {
        usernameCheckStatus.value = '';
        usernameCheckMessage.value = '';
    }
});
</script>

<style scoped>
.register-container {
    font-family: var(--font-body);
    line-height: 1.6;
    color: var(--text-primary);
    background: var(--deep-0);
    background-image:
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 229, 255, 0.06), transparent),
        radial-gradient(ellipse 40% 30% at 80% 80%, rgba(57, 255, 20, 0.04), transparent);
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100dvh;
    padding: clamp(10px, 2.6vw, 20px);
    width: 100%;
    box-sizing: border-box;
    overflow: auto;
}

.container {
    background: var(--glass-bg-heavy);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-elevated);
    width: 100%;
    max-width: 420px;
    max-height: calc(100dvh - 24px);
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.form-header {
    background: linear-gradient(135deg, rgba(0, 229, 255, 0.15) 0%, rgba(0, 150, 170, 0.08) 100%);
    padding: 28px 24px 20px;
    text-align: center;
    border-bottom: 1px solid var(--border-subtle);
}

.form-title {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: 22px;
    margin-bottom: 4px;
    letter-spacing: 0.03em;
    color: var(--text-primary);
}
.form-title:first-child {
    background: linear-gradient(135deg, var(--neon-cyan), rgba(0, 229, 255, 0.6));
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.form-subtitle {
    font-size: var(--font-size-sm);
    color: var(--text-muted);
    font-weight: 300;
    margin-top: 6px;
}

.quick-hints {
    margin-top: 12px;
    display: grid;
    gap: 6px;
}

.hint-item {
    padding: 5px 12px;
    background: rgba(0, 229, 255, 0.06);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
}

.form-body {
    padding: 24px 28px 28px;
    flex: 1;
    overflow-y: auto;
}

.mode-switch {
    display: grid;
    grid-template-columns: 1fr 1fr;
    background: rgba(0, 0, 0, 0.25);
    border-radius: var(--radius-sm);
    padding: 2px;
    margin-bottom: 22px;
}

.mode-btn {
    border: none;
    background: transparent;
    color: var(--text-muted);
    padding: 9px 12px;
    font-family: var(--font-body);
    font-size: var(--font-size-sm);
    font-weight: 500;
    cursor: pointer;
    border-radius: 4px;
    transition: all var(--duration-fast) var(--ease-out-expo);
}
.mode-btn.active {
    background: var(--surface-1);
    color: var(--neon-cyan);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

.form-group {
    margin-bottom: 22px;
    position: relative;
}

label {
    display: block;
    margin-bottom: 8px;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 500;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.input-group {
    position: relative;
}
.captcha-row {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
}
.captcha-img {
    height: 44px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    cursor: pointer;
    background: var(--deep-2);
}
.captcha-text-fallback {
    font-family: var(--font-mono);
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 6px;
    color: var(--neon-cyan);
    padding: 8px 16px;
    background: var(--deep-2);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    user-select: none;
}
.captcha-refresh {
    background: var(--surface-0);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 18px;
    cursor: pointer;
    padding: 6px 10px;
    transition: all var(--duration-fast);
}
.captcha-refresh:hover { color: var(--neon-cyan); border-color: var(--border-active); }

.input-group .icon {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    font-size: 14px;
}

input {
    width: 100%;
    padding: 11px 12px 11px 38px;
    background: rgba(6, 11, 16, 0.5);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: var(--font-size-sm);
    outline: none;
    transition: border-color var(--duration-fast), box-shadow var(--duration-fast);
}
input:focus {
    border-color: var(--neon-cyan);
    box-shadow: 0 0 0 3px rgba(0, 229, 255, 0.08);
}
input::placeholder {
    color: var(--text-muted);
}

.avatar-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
}
.avatar-item {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: var(--surface-0);
    color: var(--text-secondary);
    padding: 8px;
    display: grid;
    justify-items: center;
    gap: 4px;
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-out-expo);
}
.avatar-item:hover {
    border-color: var(--border-active);
    background: var(--surface-hover);
}
.avatar-item.active {
    border-color: var(--neon-cyan);
    background: rgba(0, 229, 255, 0.1);
    box-shadow: var(--neon-cyan-glow);
}
.avatar-item img {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    object-fit: cover;
}
.avatar-item span {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
}

.username-check { margin-top: 6px; font-family: var(--font-mono); font-size: var(--font-size-xs); }
.username-check.success { color: var(--neon-green); }
.username-check.error { color: var(--rose-400); }
.username-check.loading { color: var(--text-muted); }

.validation-message { margin-top: 6px; font-size: var(--font-size-xs); display: none; }
.validation-message.error { color: var(--rose-400); display: block; }
.validation-message.success { color: var(--neon-green); display: block; }

.quick-action-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-top: 12px;
    margin-bottom: 18px;
}
.quick-btn {
    border: 1px solid var(--border-subtle);
    background: var(--surface-0);
    color: var(--text-secondary);
    border-radius: var(--radius-sm);
    padding: 10px 8px;
    font-family: var(--font-body);
    font-size: var(--font-size-sm);
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-out-expo);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
}
.quick-btn:hover:not(:disabled) {
    border-color: var(--border-active);
    color: var(--neon-cyan);
    background: var(--surface-hover);
}
.quick-btn.guest-login {
    border-color: rgba(57, 255, 20, 0.2);
    background: rgba(57, 255, 20, 0.05);
    color: var(--neon-green);
}
.quick-btn.guest-login:hover:not(:disabled) {
    border-color: rgba(57, 255, 20, 0.4);
    box-shadow: var(--neon-green-glow);
}
.quick-btn.confirm-login {
    border-color: var(--border-active);
    background: rgba(0, 229, 255, 0.1);
    color: var(--neon-cyan);
    font-weight: 600;
}
.quick-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
}

.btn {
    display: block;
    width: 100%;
    background: linear-gradient(135deg, rgba(0, 229, 255, 0.2), rgba(0, 180, 210, 0.1));
    border: 1px solid var(--border-active);
    color: var(--neon-cyan);
    padding: 13px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: var(--font-body);
    font-size: var(--font-size-md);
    font-weight: 600;
    transition: all var(--duration-fast) var(--ease-out-expo);
    text-align: center;
    margin-top: 18px;
    letter-spacing: 0.04em;
}
.btn:hover {
    background: rgba(0, 229, 255, 0.25);
    box-shadow: var(--neon-cyan-glow);
}
.btn:active { transform: scale(0.98); }
.btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
}

.login-link {
    text-align: center;
    margin-top: 16px;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-muted);
}
.login-link a {
    color: var(--neon-cyan);
    text-decoration: none;
}
.login-link a:hover {
    text-decoration: underline;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
}
.fade-in {
    animation: fadeIn 0.5s var(--ease-out-expo) forwards;
}

.form-footer {
    padding: 14px 24px;
    text-align: center;
    background: rgba(0, 0, 0, 0.2);
    border-top: 1px solid var(--border-subtle);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-muted);
    flex-shrink: 0;
}

.default-login-hint {
    margin-top: 10px;
    padding: 5px 12px;
    background: rgba(0, 229, 255, 0.06);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    display: inline-block;
}

@media (max-width: 768px) {
    .register-container {
        align-items: stretch;
        padding: 8px;
    }
    .container {
        max-width: 100%;
        border-radius: var(--radius-md);
        max-height: none;
        min-height: calc(100dvh - 16px);
    }
    .form-body { padding: 18px; }
    .form-header { padding: 18px; }
    .form-title { font-size: 20px; }
    .form-footer { padding: 12px 16px; }
    .avatar-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
</style>

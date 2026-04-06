import { createRouter, createWebHistory } from 'vue-router'
import BasicLayout from '../components/Layout/BasicLayout.vue'
import Login from '../views/Login.vue'
import ChangePassword from '../views/ChangePassword.vue'
import EditUser from '../views/EditUser.vue'
import AddSubscription from '../views/AddSubscription.vue'
import WeChatMpManagement from '../views/WeChatMpManagement.vue'
import ConfigList from '../views/ConfigList.vue'
import ConfigDetail from '../views/ConfigDetail.vue'
import MessageTaskList from '../views/MessageTaskList.vue'
import MessageTaskForm from '../views/MessageTaskForm.vue'
import NovelReader from '../views/NovelReader.vue'
import Favorites from '../views/Favorites.vue'
import ChannelsPublic from '../views/ChannelsPublic.vue'
import InfoLayout from '../views/InfoLayout.vue'
import ManageLayout from '../views/ManageLayout.vue'

const routes = [
  {
    path: '/',
    component: BasicLayout,
    children: [
      {
        path: '',
        redirect: '/channels'
      },
      {
        path: 'change-password',
        name: 'ChangePassword',
        component: ChangePassword,
        meta: { requiresAuth: true }
      },
      {
        path: 'edit-user',
        name: 'EditUser',
        component: EditUser,
        meta: { requiresAuth: true }
      },
      {
        path: 'add-subscription',
        name: 'AddSubscription',
        component: AddSubscription,
        meta: { requiresAuth: true }
      },
      {
        path: 'wechat/mp',
        name: 'WeChatMpManagement',
        component: WeChatMpManagement,
        meta: { 
          requiresAuth: true,
          permissions: ['wechat:manage'] 
        }
      },
      
      {
        path: 'configs',
        redirect: () => ({ path: '/info/configs' })
      },
      {
        path: 'starter-pack',
        redirect: () => ({ path: '/info/starter-pack' })
      },
      {
        path: 'export/records',
        redirect: '/favorites',
      },
      {
        path: 'favorites',
        name: 'Favorites',
        component: Favorites,
        meta: {
          requiresAuth: true
        }
      },
      {
        path: 'channels',
        name: 'ChannelsPublic',
        component: ChannelsPublic,
        meta: { requiresAuth: false }
      },
      {
        path: 'manage',
        component: ManageLayout,
        meta: { requiresAuth: true },
        children: [
          { path: '', redirect: '/manage/topics' },
          { path: 'subscriptions', redirect: '/channels' },
          {
            path: 'topics',
            name: 'ManageTopics',
            component: () => import('@/views/TagList.vue'),
            meta: { requiresAuth: true, permissions: ['tag:view'] },
          },
          {
            path: 'topics/add',
            name: 'ManageTopicAdd',
            component: () => import('@/views/TagForm.vue'),
            meta: { requiresAuth: true, permissions: ['tag:edit'] },
          },
          {
            path: 'topics/edit/:id',
            name: 'ManageTopicEdit',
            component: () => import('@/views/TagForm.vue'),
            props: true,
            meta: { requiresAuth: true, permissions: ['tag:edit'] },
          },
        ],
      },
      {
        path: 'configs/:key',
        redirect: (to) => ({ path: `/info/configs/${to.params.key}` })
      },
      {
        path: 'message-tasks',
        name: 'MessageTaskList',
        component: MessageTaskList,
        meta: { 
          requiresAuth: true,
          permissions: ['message_task:view'] 
        }
      },
      {
        path: 'message-tasks/add',
        name: 'MessageTaskAdd',
        component: MessageTaskForm,
        meta: { 
          requiresAuth: true,
          permissions: ['message_task:edit'] 
        }
      },
      {
        path: 'message-tasks/edit/:id',
        name: 'MessageTaskEdit',
        component: MessageTaskForm,
        props: true,
        meta: { 
          requiresAuth: true,
          permissions: ['message_task:edit'] 
        }
      },
      {
        path: 'info',
        component: InfoLayout,
        children: [
          {
            path: '',
            redirect: '/info/system',
          },
          {
            path: 'system',
            name: 'SysInfo',
            component: () => import('@/views/SysInfo.vue'),
            meta: {
              requiresAuth: true,
              permissions: ['admin'],
            },
          },
          {
            path: 'configs',
            name: 'ConfigList',
            component: ConfigList,
            meta: {
              requiresAuth: true,
              permissions: ['config:view'],
            },
          },
          {
            path: 'configs/:key',
            name: 'ConfigDetail',
            component: ConfigDetail,
            props: true,
            meta: {
              requiresAuth: true,
              permissions: ['config:view'],
            },
          },
          {
            path: 'starter-pack',
            name: 'StarterPackConfig',
            component: () => import('@/views/StarterPackConfig.vue'),
            meta: {
              requiresAuth: true,
              permissions: ['admin'],
            },
          },
          {
            path: 'models',
            redirect: '/info/starter-pack',
            meta: {
              requiresAuth: true,
              permissions: ['admin'],
            },
          },
        ],
      },
      {
        path: 'sys-info',
        redirect: () => ({ path: '/info/system' })
      },
      {
        path: 'tags',
        redirect: '/manage/topics',
        meta: { requiresAuth: true, permissions: ['tag:view'] },
      },
      {
        path: 'tags/add',
        redirect: '/manage/topics/add',
        meta: { requiresAuth: true, permissions: ['tag:edit'] },
      },
      {
        path: 'tags/edit/:id',
        redirect: (to) => ({ path: `/manage/topics/edit/${to.params.id}` }),
        meta: { requiresAuth: true, permissions: ['tag:edit'] },
      },
    ]
  },
  {
    path: '/login',
    name: 'Login',
    component: Login
  },
  {
        path: '/reader',
        name: 'NovelReader',
        component: NovelReader,
        meta: { requiresAuth: true }
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

router.beforeEach(async (to, from, next) => {
  if (to.path === '/login') {
    return next({ path: '/channels', query: { auth: '1', tab: 'login', redirect: '/channels' } })
  }

  // 不需要认证的路由直接放行
  if (!to.meta.requiresAuth) {
    return next()
  }

  const token = localStorage.getItem('token')
  
  // 未登录则跳转登录页
  if (!token) {
    return next({
      path: '/channels',
      query: { auth: '1', tab: 'login', redirect: to.fullPath } // 首页弹框登录
    })
  }
  // 已登录状态下，不再每次路由跳转都强制验 token。
  // 仅在访问管理员页面时，按需获取一次用户角色。
  const requiredPermissions = Array.isArray(to.meta?.permissions) ? (to.meta.permissions as string[]) : []
  const needsAdmin = requiredPermissions.includes('admin') || to.path.startsWith('/info')
  if (!needsAdmin) {
    return next()
  }

  let role = String(localStorage.getItem('current_user_role') || '').trim().toLowerCase()
  if (role === 'admin') {
    return next()
  }

  try {
    const { getCurrentUser } = await import('@/api/auth')
    const user: any = await getCurrentUser()
    role = String(user?.role || '').trim().toLowerCase()
    localStorage.setItem('current_user_role', role || 'user')
    if (role !== 'admin') return next('/channels')
    return next()
  } catch (error: any) {
    const msg = String(error?.message || error || '').toLowerCase()
    const isAuthError =
      msg.includes('401') ||
      msg.includes('could not validate credentials') ||
      msg.includes('session_expired') ||
      msg.includes('登录已过期')
    if (isAuthError) {
      localStorage.removeItem('token')
      localStorage.removeItem('current_user_role')
      return next({
        path: '/channels',
        query: {
          auth: '1',
          tab: 'login',
          redirect: to.fullPath,
          error: 'session_expired'
        }
      })
    }
    // 网络抖动等非认证错误：不强制登出，直接回到普通页面。
    return next('/channels')
  }
})

export default router

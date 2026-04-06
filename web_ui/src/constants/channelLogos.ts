export interface ChannelLogoPreset {
  id: string
  name: string
  cover: string
  keywords: string[]
}

export const CHANNEL_LOGO_PRESETS: ChannelLogoPreset[] = [
  {
    id: 'portal',
    name: '门户精选',
    cover: '/static/channel-logos/portal.svg',
    keywords: ['门户', '新闻', '资讯', '热点', '头条', '快讯', 'world', 'news']
  },
  {
    id: 'science',
    name: '科教文卫',
    cover: '/static/channel-logos/science.svg',
    keywords: ['科教', '教育', '科学', '医学', '健康', '文卫', '高校', 'research']
  },
  {
    id: 'finance',
    name: '商业财经',
    cover: '/static/channel-logos/finance.svg',
    keywords: ['商业', '财经', '金融', '投资', '股票', '基金', 'economy', 'finance']
  },
  {
    id: 'tech',
    name: '科技互联网',
    cover: '/static/channel-logos/tech.svg',
    keywords: ['科技', '互联网', '开发', '程序', 'ai', '算法', '开源', 'tech']
  },
  {
    id: 'startup',
    name: '创业投资',
    cover: '/static/channel-logos/startup.svg',
    keywords: ['创业', '投资', '产品', '增长', '商业化', 'start', 'vc']
  },
  {
    id: 'culture',
    name: '文化生活',
    cover: '/static/channel-logos/culture.svg',
    keywords: ['文化', '艺术', '电影', '音乐', '设计', '生活', 'travel']
  },
  {
    id: 'sports',
    name: '体育健康',
    cover: '/static/channel-logos/sports.svg',
    keywords: ['体育', '运动', '赛事', '健身', 'health', 'sport']
  },
  {
    id: 'global',
    name: '海外观察',
    cover: '/static/channel-logos/global.svg',
    keywords: ['海外', '全球', '国际', '环球', 'wsj', 'bbc', 'guardian', 'nyt']
  }
]

export const pickDefaultChannelLogo = (channelName: string): string => {
  const name = String(channelName || '').trim().toLowerCase()
  if (!name) return CHANNEL_LOGO_PRESETS[0].cover
  const matched = CHANNEL_LOGO_PRESETS.find((item) =>
    item.keywords.some((kw) => name.includes(String(kw).toLowerCase()))
  )
  return matched?.cover || CHANNEL_LOGO_PRESETS[0].cover
}

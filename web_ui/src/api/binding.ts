import http from './http'

export type WechatBindCode = {
  code: string
  expires_at?: string | null
  expires_in?: number | null
  status?: number
}

export type WechatBindingInfo = {
  user_id: string
  is_bound: boolean
  wechat_openid_masked?: string
  wechat_unionid_masked?: string
  bind_code?: WechatBindCode | null
}

export const getWechatBinding = async (): Promise<WechatBindingInfo> => {
  const data = await http.get('/wx/binding/wechat')
  return data
}

export const createWechatBindCode = async (force = false): Promise<WechatBindCode> => {
  const data = await http.post('/wx/binding/wechat/code', { force })
  return data
}

export const RES_BASE_URL = "/static/res/logo/"
export const Avatar = (url) => {
  if (url.startsWith('http://') || url.startsWith('https://')) {
      return `${RES_BASE_URL}${url}`;
    }
    return url;
}
export const ProxyImage=(content) =>{
   if (!content) return content
   let html = String(content)
   // protocol-relative url -> https
   html = html.replace(/(<img[^>]*?\s(?:src|data-src)=["'])(\/\/[^"']+)/gi, `$1https:$2`)
   // normalize data-src -> src (WeChat articles commonly use data-src)
   html = html.replace(/<img([^>]*?)\sdata-src=["']([^"']+)["']([^>]*?)>/gi, (m, a, u, b) => {
     const out = String(m)
     const srcMatch = out.match(/\ssrc=["']([^"']*)["']/i)
     const srcVal = (srcMatch?.[1] || '').trim()
     const shouldOverride =
       !srcMatch ||
       !srcVal ||
       srcVal.startsWith('data:') ||
       srcVal.startsWith('blob:') ||
       srcVal === 'about:blank'
     if (!shouldOverride) return out
     if (srcMatch) {
       return out.replace(srcMatch[0], ` src="${u}"`)
     }
     return `<img${a} src="${u}"${b}>`
   })
   // proxy external src/data-src images through backend (avoid referrer/cors issues)
   html = html.replace(/(<img[^>]*?\s(?:src|data-src)=["'])(https?:\/\/[^"']+)/gi, `$1${RES_BASE_URL}$2`)
   // remove width attr to keep responsive
   html = html.replace(/<img([^>]*)\swidth=["'][^"']*["']([^>]*)>/gi, '<img$1$2>')
   // add referrerpolicy if missing
   html = html.replace(/<img(?![^>]*referrerpolicy=)([^>]*)>/gi, '<img referrerpolicy="no-referrer"$1>')
   return html
}

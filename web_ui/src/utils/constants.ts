export const RES_BASE_URL = "/static/res/logo/"
export const Avatar = (url) => {
  if (url.startsWith('http://') || url.startsWith('https://')) {
      return `${RES_BASE_URL}${url}`;
    }
    return url;
}
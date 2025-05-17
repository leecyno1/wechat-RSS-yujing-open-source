import dayjs from 'dayjs'

export const formatDateTime = (date: string | Date | undefined) => {
  if (!date) return '-'
  return dayjs(date).format('YYYY-MM-DD HH:mm')
}
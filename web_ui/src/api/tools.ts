import http from './http'

export const exportArticles = (params:any) => {
    const requestData = {
      mp_id: params.mp_id || '',
      export_scope: params.export_scope || 'selected',
      export_key: params.export_key || '',
      doc_id: params.scope === 'selected' ? params.ids : [],
      page_size: params.limit||10,
      page_count: params.page_count || 1,
      add_title: params.add_title !== false,
      remove_images: params.remove_images === true,
      remove_links: params.remove_links === true,
      export_md: (params.format || []).includes('md'),
      export_docx: (params.format || []).includes('docx'),
      export_json: (params.format || []).includes('json'),
      export_csv: (params.format || []).includes('csv'),
      export_pdf: (params.format || []).includes('pdf'),
      zip_filename: params.zip_filename||''
    };
  return http.post<{code: number, data: string}>('/wx/tools/export/articles', requestData, {
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    }
  })
}
export const getExportRecords = (params:any) => {
    const requestData = {
      mp_id: params.mp_id || '',
      export_key: params.export_key || '',
    };
  return http.get<{code: number, data: string}>('/wx/tools/export/list', {params:requestData})
}
export const DeleteExportRecords = (params:any) => {
    const requestData = {
      mp_id: params.mp_id || params.export_key || "",
      filename: params.filename,
    };
  return http.delete<{code: number, data: string}>('/wx/tools/export/delete', {data:requestData})
}

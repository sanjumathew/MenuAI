<script>
  import { onMount } from 'svelte'
  import { fade } from 'svelte/transition'
  let file
  let fileInput
  // raw OCR lines (not shown directly)
  let rawLines = []
  let cleaned = []
  let jobTextId = null
  let status = ''
  let useLLM = true
  let errorMessage = ''
  let generateAll = false
  let numImagesToGenerate = 2
  let showCostWarning = false
  let estimatedCost = 0
  const costPerImage = 0.02 // $0.02 per image (adjust as needed)
  $: loading = status === 'uploading' || status === 'generating'
  $: numItemsToGenerate = generateAll ? cleaned.length : numImagesToGenerate
  $: estimatedCost = numItemsToGenerate * costPerImage

  async function analyze() {
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    status = 'uploading'
    const res = await fetch('/api/upload', { method: 'POST', body: fd })
    const data = await res.json()
    jobTextId = data.job_text_id
    // store raw OCR lines but do not display them
    rawLines = (data.candidates || []).map(c=>c.text)
    // Clean extracted OCR candidates (heuristics or LLM)
    try {
      errorMessage = ''
      const cleanRes = await fetch('/api/clean_items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lines: rawLines, options: { use_llm: useLLM, include_descriptions: useLLM } })
      })
      const cleanData = await cleanRes.json()
      if (!cleanRes.ok) {
        errorMessage = cleanData.detail || JSON.stringify(cleanData)
        cleaned = rawLines.map((t,i)=>({ id: String(i), name: t }))
      } else {
        cleaned = cleanData.candidates || []
      }
    } catch (e) {
      errorMessage = String(e)
      cleaned = rawLines.map((t,i)=>({ id: String(i), name: t }))
    }
    status = 'ready'
  }

  async function confirm() {
    if (generateAll) {
      showCostWarning = true
      return
    }
    proceedWithGeneration()
  }

  function proceedWithGeneration() {
    showCostWarning = false
    status = 'generating'
    errorMessage = ''
    // Determine number of items to generate
    const source = (cleaned.length ? cleaned : rawLines.map((t,i)=>({ id: String(i), name: t })))
    const numToPick = generateAll ? source.length : Math.min(numImagesToGenerate, source.length)
    
    if (numToPick === 0) {
      errorMessage = 'No items to generate.'
      status = 'ready'
      return
    }
    
    let selectedIdxs
    if (generateAll) {
      // Generate for all items
      selectedIdxs = Array.from({ length: source.length }, (_, i) => i)
    } else {
      // Pick random items (Fisher-Yates shuffle)
      const idxs = Array.from({ length: source.length }, (_, i) => i)
      for (let i = idxs.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[idxs[i], idxs[j]] = [idxs[j], idxs[i]]
      }
      selectedIdxs = idxs.slice(0, numToPick)
    }
    
    const selectedIdsSet = new Set(selectedIdxs.map(i => source[i].id))
    const toGenerate = selectedIdxs.map(i => ({ id: source[i].id, text: source[i].name || source[i].text, prompt: source[i].prompt }))

    const options = { use_llm: useLLM }

    fetch('/api/generate_images', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ items: toGenerate, options }) })
      .then(res => res.json())
      .then(data => {
        if (!data || (data.detail || data.error)) {
          errorMessage = data.detail || data.error || JSON.stringify(data)
          status = 'ready'
          return
        }
        // attach images to source list
        const results = data.results || {}
        for (const it of toGenerate) {
          const r = results[it.id]
          const idx = source.findIndex(s=>s.id==it.id)
          if (r && r.status==='ok') {
            source[idx].image = r.image
            source[idx].status = 'ready'
          } else {
            source[idx].status = 'error'
            source[idx].error = r && r.error
          }
        }
        // reflect back into cleaned
        // sort so selected items come first, then items with images, then the rest
        source.sort((a, b) => {
          const aSel = selectedIdsSet.has(a.id) ? 1 : 0
          const bSel = selectedIdsSet.has(b.id) ? 1 : 0
          if (aSel !== bSel) return bSel - aSel
          const aImg = a.image ? 1 : 0
          const bImg = b.image ? 1 : 0
          if (aImg !== bImg) return bImg - aImg
          return 0
        })
        cleaned = source
        status = 'completed'
      })
      .catch(e => {
        errorMessage = String(e)
        status = 'ready'
      })
  }

  async function pollJob(jobId) {
    const iv = setInterval(async ()=>{
      const res = await fetch(`/api/job/${jobId}`)
      const data = await res.json()
      // map results to cleaned
      for (const id in data.items) {
        const it = data.items[id]
        const idx = cleaned.findIndex(c=>c.id==id)
        if (it.status === 'ready' && it.image) {
          cleaned[idx].image = it.image
          cleaned[idx].status = 'ready'
        } else {
          cleaned[idx].status = it.status
        }
      }
      // keep items with images on top while polling
      cleaned.sort((a,b)=> {
        const aImg = a.image ? 1 : 0
        const bImg = b.image ? 1 : 0
        return bImg - aImg
      })

      if (data.status === 'completed') {
        clearInterval(iv)
        status = 'completed'
      }
    }, 1500)
  }
</script>

<main class="container py-4">
  {#if loading}
    <div class="page-loader" role="status" aria-live="polite">
      <div class="loader-box text-center text-white">
        <div class="spinner-border text-light" role="status" style="width:4rem;height:4rem">
          <span class="visually-hidden">Loading...</span>
        </div>
        <div class="mt-3">{status === 'uploading' ? 'Processing & cleaning...' : status === 'generating' ? 'Generating images...' : 'Loading...'}</div>
      </div>
    </div>
  {/if}
  <div class="d-flex align-items-center mb-3">
    <h1 class="me-3 mb-0 app-title text-white">Menu AI</h1>
    <div class="ms-auto d-flex align-items-center gap-2">
      <input class="form-check-input" type="checkbox" bind:checked={useLLM} id="useLLM" />
      <label class="form-check-label text-white" for="useLLM">Use LLM for cleaning</label>
    </div>
  </div>

  <div class="mb-3 d-flex gap-2 align-items-center">
    <input class="form-control form-control-sm file-input" type="file" bind:this={fileInput} on:change={(e)=>file=e.target.files[0]} />
    <button class="btn btn-primary btn-sm" on:click={analyze}>Analyze</button>
    
    {#if cleaned.length > 0}
      <div class="d-flex align-items-center gap-2 ms-auto">
        <input class="form-check-input" type="checkbox" bind:checked={generateAll} id="generateAll" />
        <label class="form-check-label text-white" for="generateAll">Generate all ({cleaned.length})</label>
        
        {#if !generateAll}
          <div class="d-flex align-items-center gap-2">
            <label class="form-check-label text-white mb-0 ms-2" for="numImages">Images:</label>
            <input class="form-control form-control-sm" type="number" bind:value={numImagesToGenerate} id="numImages" min="1" max={cleaned.length} style="width: 60px;" />
          </div>
        {/if}
        
        <button class="btn btn-success btn-sm" on:click={confirm}>
          {generateAll ? `Generate All (${estimatedCost.toFixed(2)}$)` : `Generate (Estimated: ${estimatedCost.toFixed(2)}$)`}
        </button>
      </div>
    {/if}
  </div>

  {#if status}
    <div class="mb-2 text-muted">Status: {status}</div>
  {/if}
  {#if errorMessage}
    <div class="mb-2 text-danger">Error: {errorMessage}</div>
  {/if}

  <!-- Cost Warning Modal -->
  {#if showCostWarning}
    <div class="modal-backdrop" in:fade={{ duration: 200 }}>
      <div class="modal-dialog" in:fade={{ duration: 200 }}>
        <div class="modal-content">
          <div class="modal-header bg-warning text-dark">
            <h5 class="modal-title">⚠️ Generation Cost Warning</h5>
            <button type="button" class="btn-close" on:click={() => (showCostWarning = false)}></button>
          </div>
          <div class="modal-body">
            <p>You are about to generate images for <strong>{cleaned.length} items</strong>.</p>
            <p class="mb-0">
              <strong>Estimated cost:</strong> <span class="text-success">${estimatedCost.toFixed(2)}</span>
            </p>
            <small class="text-muted d-block mt-2">Cost per image: ${costPerImage.toFixed(2)}</small>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" on:click={() => (showCostWarning = false)}>Cancel</button>
            <button type="button" class="btn btn-warning text-dark" on:click={proceedWithGeneration}>Proceed</button>
          </div>
        </div>
      </div>
    </div>
  {/if}

  {#if cleaned.length}
    <div class="row gy-3">
      {#each cleaned as c (c.id)}
        <div class="col-12 col-sm-6 col-md-4" in:fade={{ duration: 350 }}>
          <div class="card h-100 shadow-sm bg-dark text-light border-0 position-relative">
                {#if c.image}
                  <div class="position-absolute top-0 end-0 m-2">
                    <a class="btn btn-sm btn-outline-light" href={c.image} download target="_blank" rel="noopener noreferrer" aria-label="Download image">↓</a>
                  </div>
                  <img src={c.image} class="card-img-top" alt={c.name} style="height:320px; object-fit:cover" />
              {:else}
                    <div class="card-img-top d-flex align-items-center justify-content-center bg-dark text-white-50" style="height:320px">
                    {#if c.status === 'error'}
                      <div class="text-danger small">{c.error || 'error'}</div>
                    {:else}
                      <div class="spinner-border text-light" role="status" style="width:3rem;height:3rem">
                        <span class="visually-hidden">Loading...</span>
                      </div>
                    {/if}
                  </div>
              {/if}
              <div class="card-body d-flex flex-column bg-transparent">
                <h5 class="card-title mb-2">{c.name}</h5>
                <p class="card-text text-white-50 mt-auto small">{c.description || ''}</p>
              {#if c.error}
                <div class="text-danger small mt-2">{c.error}</div>
              {/if}
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</main>

<style>
  :global(body) { margin:0; font-family: Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; background: #0b0f14; color: #e6eef8 }
  main { max-width: 1200px; margin: 24px auto; padding: 24px; }
  h1 { margin: 0 0 12px 0; font-size: 20px }
  label { font-size:13px }
  .app-title { font-size:1.6rem; font-weight:700; letter-spacing:0.2px }
  .file-input { min-width:220px; }
  p { margin:8px 0 }

  /* Dark card styling */
  .card {
    background: linear-gradient(180deg, rgba(11,15,20,0.6), rgba(8,10,12,0.6));
    border: 1px solid rgba(255,255,255,0.04);
    min-height: 450px;
  }
  .card .card-img-top {
    border-bottom: 1px solid rgba(255,255,255,0.03);
  }
  .card .card-body { background: transparent }
  .card .card-title { color: #ffffff }
  .card .card-text { color: rgba(230,238,248,0.65) }
  .card .btn-outline-light { padding: 0.35rem 0.5rem; font-size:0.9rem }
  /* Full-page loader */
  .page-loader {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1050;
    pointer-events: all;
  }
  .loader-box { padding: 1.25rem 1.75rem; border-radius: 8px }

  /* Modal styles */
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1060;
  }
  .modal-dialog {
    background: #0b0f14;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    max-width: 500px;
    width: 90%;
  }
  .modal-content {
    background: #0b0f14;
    border: 1px solid rgba(255,255,255,0.1);
    color: #e6eef8;
  }
  .modal-header {
    border-bottom: 1px solid rgba(255,255,255,0.1);
  }
  .modal-footer {
    border-top: 1px solid rgba(255,255,255,0.1);
  }
</style>

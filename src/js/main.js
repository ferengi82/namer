// noinspection ES6UnusedImports
// eslint-disable-next-line no-unused-vars
import { Modal, Popover } from 'bootstrap'

import $ from 'jquery'
import 'datatables.net-bs5'
import 'datatables.net-colreorder-bs5'
import 'datatables.net-buttons/js/buttons.colVis'
import 'datatables.net-buttons-bs5'
import 'datatables.net-responsive'
import 'datatables.net-responsive-bs5'
import 'datatables.net-fixedheader'
import 'datatables.net-fixedheader-bs5'
import { escape } from 'lodash'

import { Helpers } from './helpers'
import './themes'

window.jQuery = $

const filesResult = $('#filesResult')
const tableButtons = $('#tableButtons')
const resultForm = $('#searchResults .modal-body')
const resultFormTitle = $('#modalSearchResultsLabel span')
const logForm = $('#logFile .modal-body')
const logFormTitle = $('#modalLogsLabel span')
const searchForm = $('#searchForm')
const searchButton = $('#searchForm .modal-footer .search')
const phashButton = $('#searchForm .modal-footer .phash')
const queryInput = $('#queryInput')
const queryType = $('#queryType')
const deleteFile = $('#deleteFile')
const queueSize = $('#queueSize')
const refreshFiles = $('#refreshFiles')
const deleteButton = $('#deleteButton')
const videoPlayerModal = $('#videoPlayer')
const logFilePlayBtn = $('#logFilePlayBtn')
const searchResultsPlayBtn = $('#searchResultsPlayBtn')

let modalButton

searchButton.on('click', function () {
  resultForm.html(Helpers.getProgressBar())

  const data = {
    query: queryInput.val(),
    file: queryInput.data('file'),
    type: queryType.val()
  }

  const title = escape(`(${data.file}) [${data.query}]`)
  resultFormTitle.html(title)
  resultFormTitle.attr('title', title)
  showSearchResultsPlayBtn(data.file)

  Helpers.request('./api/v1/get_search', data, function (data) {
    Helpers.render('searchResults', data, resultForm, function (selector) {
      Helpers.initTooltips(selector)
    })
  })
})

phashButton.on('click', function () {
  resultForm.html(Helpers.getProgressBar())

  const data = {
    file: queryInput.data('file'),
    type: queryType.val()
  }

  const title = escape(`(${data.file})`)
  resultFormTitle.html(title)
  resultFormTitle.attr('title', title)
  showSearchResultsPlayBtn(data.file)

  Helpers.request('./api/v1/get_phash', data, function (data) {
    Helpers.render('searchResults', data, resultForm, function (selector) {
      Helpers.initTooltips(selector)
    })
  })
})

queryInput.on('keyup', function (e) {
  if (e.which === 13) {
    searchButton.click()
  }
})

filesResult.on('click', '.match', function () {
  modalButton = $(this)
  const query = modalButton.data('query')
  const file = modalButton.data('file')
  queryInput.val(query)
  queryInput.data('file', file)
})

filesResult.on('click', '.log', function () {
  logForm.html(Helpers.getProgressBar())
  modalButton = $(this)
  const data = {
    file: modalButton.data('file')
  }

  const title = escape(`[${data.file}]`)

  logFormTitle.html(title)
  logFormTitle.attr('title', title)
  showLogFilePlayBtn(data.file)

  Helpers.request('./api/v1/read_failed_log', data, function (data) {
    Helpers.render('logFile', data, logForm, function (selector) {
      Helpers.initTooltips(selector)
    })
  })
})

filesResult.on('click', '.play', function () {
  const file = $(this).data('file')
  const name = $(this).data('name')
  openVideoPlayer(file, name)
})

logFilePlayBtn.on('click', function () {
  openVideoPlayer($(this).data('file'), $(this).data('file'))
})

searchResultsPlayBtn.on('click', function () {
  openVideoPlayer($(this).data('file'), $(this).data('file'))
})

videoPlayerModal.on('hidden.bs.modal', function () {
  const videoEl = document.getElementById('videoPlayerEl')
  if (videoEl) {
    videoEl.pause()
    videoEl.removeAttribute('src')
    videoEl.load()
  }
  const errorEl = document.getElementById('videoPlayerError')
  if (errorEl) {
    errorEl.classList.add('d-none')
    errorEl.textContent = ''
  }
})

function openVideoPlayer (file, name) {
  if (!file) {
    return
  }
  const videoEl = document.getElementById('videoPlayerEl')
  const errorEl = document.getElementById('videoPlayerError')
  const titleSpan = $('#modalVideoLabel span')
  titleSpan.text(name || file)
  titleSpan.attr('title', name || file)
  errorEl.classList.add('d-none')
  errorEl.textContent = ''
  const src = `./api/v1/stream?file=${encodeURIComponent(file)}`
  videoEl.src = src
  videoEl.load()
  videoEl.onerror = function () {
    errorEl.textContent = 'Video konnte nicht geladen oder abgespielt werden.'
    errorEl.classList.remove('d-none')
  }
}

function showLogFilePlayBtn (file) {
  if (!file) {
    logFilePlayBtn.addClass('d-none')
    return
  }
  logFilePlayBtn.data('file', file)
  logFilePlayBtn.removeClass('d-none')
}

function showSearchResultsPlayBtn (file) {
  if (!file) {
    searchResultsPlayBtn.addClass('d-none')
    return
  }
  searchResultsPlayBtn.data('file', file)
  searchResultsPlayBtn.removeClass('d-none')
}

filesResult.on('click', '.delete', function () {
  modalButton = $(this)
  const file = modalButton.data('file')
  deleteFile.val(file)
  deleteFile.data('file', file)
})

refreshFiles.on('click', function () {
  Helpers.refreshFiles(filesResult, tableButtons, $(this).data('target'))
  if (queueSize) {
    Helpers.updateQueueSize(queueSize)
  }
})

searchForm.on('shown.bs.modal', function () {
  queryInput.focus()
})

resultForm.on('click', '.rename', rename)
logForm.on('click', '.rename', rename)

deleteButton.on('click', function () {
  const data = {
    file: deleteFile.data('file')
  }

  Helpers.request('./api/v1/delete', data, function () {
    Helpers.removeRow(modalButton)
  })
})

function rename () {
  const data = {
    file: $(this).data('file'),
    scene_id: $(this).data('scene-id')
  }

  Helpers.request('./api/v1/rename', data, function () {
    Helpers.removeRow(modalButton)
  })
}

Helpers.setTableSort(filesResult, tableButtons)

if (queueSize) {
  Helpers.updateQueueSize(queueSize)
  setInterval(function () {
    Helpers.updateQueueSize(queueSize)
  }, 5000)
}

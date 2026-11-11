# Inline SVG icons (24x24, stroke) ----------------------------------------------------------

.dr_icons <- list(
  logo = '<path d="M4 8.5h16v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><path d="m4 8.5 1.2-4a1.5 1.5 0 0 1 1.8-1l12.6 3.6-1.1 3.9"/><path d="m8.6 4.4 2.6 4M13.6 5.8l2.6 4"/><path d="m10.5 12.5 4 2.25-4 2.25z" fill="currentColor"/>',
  library = '<rect x="3" y="3" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2"/>',
  source = '<path d="M10 13.5a4.5 4.5 0 0 0 6.4.4l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.6 1.6"/><path d="M14 10.5a4.5 4.5 0 0 0-6.4-.4l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.6-1.6"/>',
  story = '<path d="M4 5h16M4 10h10M4 15h16M4 20h7"/>',
  shots = '<rect x="2.5" y="6" width="14" height="12" rx="2.5"/><path d="m16.5 10.5 5-3v9l-5-3z"/>',
  sound = '<path d="M9 18V6l11-2.5v12"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="15.5" r="3"/>',
  look = '<circle cx="12" cy="12" r="9.5"/><circle cx="8" cy="10" r="1.4" fill="currentColor"/><circle cx="12" cy="7.2" r="1.4" fill="currentColor"/><circle cx="16" cy="10" r="1.4" fill="currentColor"/><path d="M12 21.5a2.5 2.5 0 0 1 0-5h2a3 3 0 0 0 3-3"/>',
  export = '<path d="M12 3v12m0 0-4.5-4.5M12 15l4.5-4.5"/><path d="M4 16.5V19a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2.5"/>',
  sparkles = '<path d="M12 3.5l1.7 4.6 4.6 1.7-4.6 1.7L12 16.1l-1.7-4.6-4.6-1.7 4.6-1.7z"/><path d="M19 14.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8zM5 3l.6 1.5L7 5.1l-1.4.6L5 7.2l-.6-1.5L3 5.1l1.4-.6z"/>',
  play = '<path d="M7 4.8v14.4a1 1 0 0 0 1.5.9l11.6-7.2a1 1 0 0 0 0-1.8L8.5 3.9A1 1 0 0 0 7 4.8z" fill="currentColor"/>',
  pause = '<rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor"/><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor"/>',
  link = '<path d="M10 13.5a4.5 4.5 0 0 0 6.4.4l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.6 1.6"/><path d="M14 10.5a4.5 4.5 0 0 0-6.4-.4l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.6-1.6"/>',
  zip = '<path d="M6 2.5h8.5L19 7v13.5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-17a1 1 0 0 1 1-1z"/><path d="M14 2.5V7h5M10 5h1.5M10 8h1.5M10 11h1.5M9.5 14h2.5v3.5H9.5z"/>',
  folder = '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.2l2 2.2h8.8A1.5 1.5 0 0 1 21 8.7v9.8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/>',
  image = '<rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="9" cy="9.5" r="1.8"/><path d="m21 15.5-5-5-9.5 9.5"/>',
  git = '<circle cx="6" cy="5.5" r="2.3"/><circle cx="6" cy="18.5" r="2.3"/><circle cx="18" cy="8" r="2.3"/><path d="M6 7.8v8.4M18 10.3c0 4-6 3.2-10.2 6.4"/>',
  globe = '<circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19M12 2.5c3 3.2 3 15.8 0 19M12 2.5c-3 3.2-3 15.8 0 19"/>',
  upload = '<path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5"/><path d="M4 15v3.5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V15"/>',
  check = '<path d="m4.5 12.5 5 5 10-11"/>',
  x = '<path d="M6 6l12 12M18 6 6 18"/>',
  plus = '<path d="M12 5v14M5 12h14"/>',
  trash = '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l.9 12.1a1.5 1.5 0 0 0 1.5 1.4h6.2a1.5 1.5 0 0 0 1.5-1.4L17.5 7"/>',
  copy = '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>',
  up = '<path d="m6 14 6-6 6 6"/>',
  down = '<path d="m6 10 6 6 6-6"/>',
  refresh = '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8.5M4 4v4.5h4.5M4 13a8 8 0 0 0 14.5 4.5l1.5-2M20 20v-4.5h-4.5"/>',
  eye = '<path d="M2.5 12S6 5 12 5s9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7z"/><circle cx="12" cy="12" r="3"/>',
  mic = '<rect x="9" y="2.5" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3.5"/>',
  stop = '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
  wand = '<path d="m4 20 11-11M13 4v2.5M18 6l-1.5 1.5M20 11h-2.5M15.5 11.5 17 13M9.5 4.5 11 6"/><path d="m13.5 7.5 3 3"/>',
  clock = '<circle cx="12" cy="12" r="9.5"/><path d="M12 6.5V12l3.5 2.5"/>',
  alert = '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.2v.3"/>',
  info = '<circle cx="12" cy="12" r="9.5"/><path d="M12 11v5.5M12 7.8v.3"/>',
  chevron = '<path d="m9 6 6 6-6 6"/>',
  external = '<path d="M14 4h6v6M20 4l-9 9M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
  monitor = '<rect x="2.5" y="4" width="19" height="13" rx="2"/><path d="M8.5 21h7M12 17v4"/>',
  phone = '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>',
  square = '<rect x="4" y="4" width="16" height="16" rx="2.5"/>',
  portrait = '<rect x="5.5" y="3" width="13" height="18" rx="2.5"/>',
  type = '<path d="M5 7V5h14v2M12 5v14M9 19h6"/>',
  cursor = '<path d="m5 3 6.5 17 2.3-6.8L20.5 11z"/>',
  layers = '<path d="m12 3 9.5 5-9.5 5-9.5-5z"/><path d="m2.5 13 9.5 5 9.5-5"/>',
  film = '<rect x="3" y="3" width="18" height="18" rx="2.5"/><path d="M7.5 3v18M16.5 3v18M3 8h4.5M3 12h18M3 16h4.5M16.5 8H21M16.5 16H21"/>',
  zap = '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  sliders = '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  volume = '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/>',
  target = '<circle cx="12" cy="12" r="9.5"/><circle cx="12" cy="12" r="5.5"/><circle cx="12" cy="12" r="1.5"/>',
  grid = '<rect x="3" y="3" width="18" height="18" rx="2.5"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
  quote = '<path d="M9.5 8H6a2 2 0 0 0-2 2v3.5h5.5V8zm0 5.5c0 3-1.5 4.5-4 5M20 8h-3.5a2 2 0 0 0-2 2v3.5H20V8zm0 5.5c0 3-1.5 4.5-4 5"/>',
  hash = '<path d="M9 3 7 21M17 3l-2 18M4 8.5h16M3.5 15.5h16"/>',
  flag = '<path d="M5 21V4M5 4.5c5-3 9 3 14 0v9c-5 3-9-3-14 0"/>',
  terminal = '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="m7 9 3 3-3 3M12.5 15h4.5"/>',
  key = '<circle cx="8" cy="15" r="4.5"/><path d="m11.3 11.8 8.7-8.8M17 6l2.5 2.5M14.5 8.5l2 2"/>',
  dots = '<circle cx="5" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="19" cy="12" r="1.6" fill="currentColor"/>',
  settings = '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'
)

#' An inline SVG icon
#' @param name Icon name (see `names(.dr_icons)`).
#' @param size Pixel size.
#' @param class Extra CSS class.
#' @return An `htmltools` HTML string.
#' @keywords internal
dr_icon <- function(name, size = 18, class = NULL) {
  path <- .dr_icons[[name]] %||% .dr_icons$sparkles
  htmltools::HTML(sprintf('<svg class="ic%s" width="%d" height="%d" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>',
                          if (is.null(class)) "" else paste0(" ", class), size, size, path))
}

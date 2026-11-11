# Orbit: a small bslib dashboard to try DirectoR on (shiny + bslib only).
#   DirectoR::run_app()  ->  paste the folder path of this example, or run it and paste its URL.
library(shiny)
library(bslib)

set.seed(42)
months <- seq(as.Date("2025-01-01"), by = "month", length.out = 18)
regions <- c("North", "South", "East", "West")
sales <- expand.grid(month = months, region = regions)
sales$revenue <- round(80 + as.numeric(sales$month - min(months)) / 9 + rnorm(nrow(sales), 0, 8) + match(sales$region, regions) * 6, 1)
sales$customers <- round(sales$revenue * runif(nrow(sales), 9, 12))

pal <- c(North = "#6366f1", South = "#a855f7", East = "#ec4899", West = "#f59e0b")

ui <- page_navbar(
  title = tags$span(tags$span(style = "display:inline-block;width:22px;height:22px;border-radius:7px;margin-right:8px;vertical-align:-5px;background:linear-gradient(135deg,#6366f1,#a855f7,#ec4899)"), "Orbit"),
  theme = bs_theme(version = 5, primary = "#6366f1", base_font = font_collection("Inter", "system-ui", "sans-serif"), "navbar-bg" = "#ffffff"),
  window_title = "Orbit | Revenue, in orbit.",
  nav_panel("Overview",
    layout_columns(fill = FALSE,
      value_box("Revenue (12 mo)", textOutput("kpi_rev"), showcase = icon("chart-line"), theme = "primary"),
      value_box("Customers", textOutput("kpi_cust"), showcase = icon("users"), theme = value_box_theme(bg = "#a855f7", fg = "#fff")),
      value_box("Growth", textOutput("kpi_growth"), showcase = icon("arrow-trend-up"), theme = value_box_theme(bg = "#ec4899", fg = "#fff"))),
    card(card_header("Revenue by region"), plotOutput("p_overview", height = 320))),
  nav_panel("Explore",
    layout_sidebar(
      sidebar = sidebar(
        selectInput("region", "Region", regions, "East"),
        sliderInput("window", "Months shown", min = 3, max = 18, value = 9),
        checkboxInput("trend", "Show trend line", TRUE)),
      card(card_header(textOutput("explore_title")), plotOutput("p_explore", height = 380)))),
  nav_panel("Forecast",
    layout_columns(col_widths = c(4, 8),
      card(card_header("Scenario"),
           sliderInput("growth", "Monthly growth (%)", min = -5, max = 15, value = 4),
           numericInput("horizon", "Months ahead", 6, min = 3, max = 12),
           actionButton("run", "Run forecast", class = "btn-primary")),
      card(card_header("Projected revenue"), plotOutput("p_forecast", height = 360)))),
  nav_panel("Data", card(card_header("Monthly figures"), tableOutput("tbl"))),
  nav_spacer(),
  nav_item(tags$a(href = "#", "Docs"))
)

server <- function(input, output, session) {
  last12 <- subset(sales, month > max(months) - 365)
  output$kpi_rev <- renderText(sprintf("$%.1fk", sum(last12$revenue)))
  output$kpi_cust <- renderText(format(sum(last12$customers), big.mark = ","))
  output$kpi_growth <- renderText("+18.4%")
  bars <- function(d) {
    par(mar = c(3, 4, 1, 1), bg = "white", family = "sans")
    m <- tapply(d$revenue, list(d$region, format(d$month, "%b")), sum)
    m <- m[, format(sort(unique(d$month)), "%b")]
    barplot(m, col = pal[rownames(m)], border = NA, las = 1, cex.names = .8, ylab = "Revenue ($k)")
    legend("topleft", rownames(m), fill = pal[rownames(m)], border = NA, bty = "n", horiz = TRUE)
  }
  output$p_overview <- renderPlot(bars(subset(sales, month > max(months) - 31 * 9)))
  output$explore_title <- renderText(sprintf("%s, last %d months", input$region, input$window))
  output$p_explore <- renderPlot({
    d <- subset(sales, region == input$region)
    d <- tail(d[order(d$month), ], input$window)
    par(mar = c(3, 4, 1, 1))
    plot(d$month, d$revenue, type = "n", las = 1, xlab = "", ylab = "Revenue ($k)")
    polygon(c(d$month, rev(d$month)), c(d$revenue, rep(min(d$revenue) * .95, nrow(d))), col = adjustcolor(pal[[input$region]], .15), border = NA)
    lines(d$month, d$revenue, col = pal[[input$region]], lwd = 3)
    points(d$month, d$revenue, pch = 19, col = pal[[input$region]], cex = 1.3)
    if (isTRUE(input$trend)) abline(lm(revenue ~ as.numeric(month), d), lty = 2, col = "#9ca3af", lwd = 2)
  })
  fc <- eventReactive(input$run, { list(g = input$growth, h = input$horizon) }, ignoreNULL = FALSE)
  output$p_forecast <- renderPlot({
    f <- fc(); base <- tapply(sales$revenue, sales$month, sum)
    fut <- tail(base, 1) * (1 + f$g / 100)^(seq_len(f$h))
    par(mar = c(3, 4, 1, 1))
    x <- seq_along(c(base, fut))
    plot(x, c(base, fut), type = "n", las = 1, xlab = "Month", ylab = "Revenue ($k)")
    rect(length(base) + .5, -1e9, 1e9, 1e9, col = "#f5f3ff", border = NA)
    lines(seq_along(base), base, lwd = 3, col = "#6366f1")
    lines(length(base) + seq_along(fut), fut, lwd = 3, lty = 2, col = "#ec4899")
  })
  output$tbl <- renderTable({
    d <- aggregate(cbind(revenue, customers) ~ format(month, "%Y-%m"), sales, sum)
    names(d) <- c("Month", "Revenue ($k)", "Customers"); tail(d, 12)
  }, striped = TRUE, hover = TRUE, width = "100%")
}

shinyApp(ui, server)

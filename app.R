# Deployment / quick start entry point.
#   Rscript -e 'shiny::runApp("DirectoR")'        (from the parent folder)
# or, with the package installed: DirectoR::run_app()
if (requireNamespace("pkgload", quietly = TRUE) && file.exists("DESCRIPTION")) {
  pkgload::load_all(".", export_all = FALSE, helpers = FALSE, quiet = TRUE)
} else {
  library(DirectoR)
}
DirectoR::director_app()

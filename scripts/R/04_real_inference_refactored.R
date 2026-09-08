# ============================================================
# 04_real_inference_refactored.R
# ------------------------------------------------------------
# Refactored real-data deck effect estimation (Arena 7-3 runs)
#
# Best-practice upgrades versus 03_real_inference.R:
#   1) Leakage control:
#      - Grouped splits by player when available.
#      - Time-based holdout when timestamp is available.
#   2) Evaluation design:
#      - Dedicated external holdout set.
#      - Nested grouped CV on development data for model selection.
#   3) Causal-use diagnostics:
#      - Overlap/support diagnostics for base skill and frequent features.
#        Checks that the model doesn't make causal claims in regions with little data support.
#        (e.g. certain deck feature patterns appearing only for certain base-skill strata)
#      - Bootstrap uncertainty interval for a g-computation estimand.
#
# Primary estimand:
#   bump(d1) = E_P[ E[W | do(D=d1), P] - E[W | do(D=d0(P)), P] ]
# W: winrate - the outcome I care about
# D: Deck representation
# P: Player skill proxy
# d1: Target deck being evaluated
# d0(P): A baseline deck choice rule that depends on player skill (e.g. typical deck for a player of that skill / observed deck distribution conditional on P)
# bump(d1): Expected improvement if we were to intervene and change the deck to be d1 instead of the baseline deck for that player
# ============================================================

suppressPackageStartupMessages({
  library(arrow)
  library(data.table)
  library(ggplot2)
  library(xgboost)
})

# ----------------------------
# Paths
# ----------------------------
decks_path <- "C:/GitHub/MTGA_DraftHelper/data/processed/decks.parquet"
figs_dir <- "C:/GitHub/High_Dimensional_Causal_Inference/figs"
models_dir <- "C:/GitHub/High_Dimensional_Causal_Inference/models"

dir.create(figs_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(models_dir, recursive = TRUE, showWarnings = FALSE)

# ----------------------------
# Utilities
# ----------------------------
clip01 <- function(p, eps = 1e-6) pmin(pmax(p, eps), 1 - eps) # Clamps probabilities so logit() doesn't blow up at 0/1
logit <- function(p) log(p / (1 - p))
invlogit <- function(z) 1 / (1 + exp(-z))

posterior_mean_p <- function(w, l, a0 = 0.5, b0 = 0.5) {
  (w + a0) / (w + l + a0 + b0)
}
# this is a beta-binomial posterior mean. with a0=b0=0.5 it’s a jeffreys prior, which gives mild shrinkage when runs have few games.

save_plot <- function(p, filename, width = 8, height = 5, dpi = 160) {
  ggsave(
    filename = file.path(figs_dir, filename),
    plot = p, width = width, height = height, dpi = dpi
  )
}

weighted_r2 <- function(y, yhat, w) {
  fit <- lm(y ~ yhat, weights = w)
  summary(fit)$r.squared
}

weighted_rmse <- function(y, yhat, w) {
  sqrt(weighted.mean((y - yhat)^2, w))
}

detect_first_col <- function(dt, candidates) {
  hit <- intersect(candidates, names(dt))
  if (length(hit) == 0L) return(NA_character_)
  hit[1]
}

create_group_folds <- function(groups, k = 5L, seed = 1L) {
  set.seed(seed)
  g <- as.character(groups)
  g[is.na(g) | g == ""] <- paste0("row_", which(is.na(g) | g == ""))
  ug <- unique(g)
  ug <- sample(ug)
  fold_of_group <- rep_len(1:k, length.out = length(ug))
  names(fold_of_group) <- ug
  fold_id <- as.integer(fold_of_group[g])
  fold_id
}

folds_list_from_id <- function(fold_id, k = 5L) {
  lapply(seq_len(k), function(i) which(fold_id == i))
}

get_best_iter_from_cv <- function(cv, metric_col = "test_rmse_mean") {
  # preferred: early stopping metadata
  if (!is.null(cv$early_stop) && !is.null(cv$early_stop$best_iteration)) {
    bi <- cv$early_stop$best_iteration
    if (!is.na(bi) && bi >= 1L) return(as.integer(bi))
  }
  
  # fallback: pick the iteration with minimum test metric
  elog <- cv$evaluation_log
  if (!is.null(elog) && metric_col %in% names(elog)) {
    m <- elog[[metric_col]]
    if (is.numeric(m) && any(is.finite(m))) {
      return(as.integer(which.min(m)))
    }
  }
  
  NA_integer_
}


tune_with_grouped_cv <- function(X, y, w, groups, param_grid, nfold = 5L, seed = 1L,
                                 nrounds = 4000L, early_stopping_rounds = 50L) {
  dtrain <- xgb.DMatrix(data = X, label = y, weight = w)
  fold_id <- create_group_folds(groups, k = nfold, seed = seed)
  folds <- folds_list_from_id(fold_id, k = nfold)

  best <- NULL
  for (i in seq_len(nrow(param_grid))) {
    params <- as.list(param_grid[i])
    params$objective <- "reg:squarederror"
    params$eval_metric <- "rmse"

    cv <- xgb.cv(
      params = params,
      data = dtrain,
      folds = folds,
      nrounds = nrounds,
      early_stopping_rounds = early_stopping_rounds,
      verbose = 0
    )

    iter <- cv$best_iteration
    rmse <- cv$evaluation_log$test_rmse_mean[iter]
    out <- list(params = params, best_nrounds = iter, rmse = rmse)

    if (is.null(best) || out$rmse < best$rmse) best <- out
  }
  best
}


tune_with_cv <- function(X, y, w, param_grid, nfold = 5L, seed = 1L,
                         nrounds = 4000L, early_stopping_rounds = 50L) {
  
  dtrain <- xgb.DMatrix(data = X, label = y, weight = w)
  n <- length(y)
  k_eff <- min(as.integer(nfold), n)
  
  best <- NULL
  
  # xgb.cv needs >= 2 folds
  if (k_eff < 2L) {
    params <- as.list(param_grid[1, , drop = FALSE])
    params$objective <- "reg:squarederror"
    params$eval_metric <- "rmse"
    return(list(params = params, best_nrounds = min(500L, nrounds), rmse = Inf))
  }
  
  set.seed(seed)
  fold_id <- sample(rep(seq_len(k_eff), length.out = n))
  folds <- lapply(seq_len(k_eff), function(k) which(fold_id == k))
  nthread <- parallel::detectCores()

  cat("tune_with_cv: n=", length(y), "k_eff=", k_eff, "grid=", nrow(param_grid), "\n","N_threads: n=",nthread, "\n")
  for (i in seq_len(nrow(param_grid))) {
    params <- as.list(param_grid[i, , drop = FALSE])
    params$objective <- "reg:squarederror"
    params$eval_metric <- "rmse"
    params$tree_method <- "hist"
    params$nthread <- nthread
    
    
    cv <- xgb.cv(
      params = params,
      data = dtrain,
      folds = folds,
      nrounds = nrounds,
      early_stopping_rounds = early_stopping_rounds,
      verbose = 0
    )
    if (i == 1) print(tail(cv$evaluation_log, 3))
    
    
    iter <- get_best_iter_from_cv(cv, metric_col = "test_rmse_mean")
    if (is.na(iter) || iter < 1L) next
    
    rmse <- cv$evaluation_log$test_rmse_mean[iter]
    if (!is.finite(rmse)) next
    
    out <- list(params = params, best_nrounds = iter, rmse = rmse)
    if (is.null(best) || out$rmse < best$rmse) best <- out
  }
  
  # if (is.null(best)) {
  #   params <- as.list(param_grid[1, , drop = FALSE])
  #   params$objective <- "reg:squarederror"
  #   params$eval_metric <- "rmse"
  #   best <- list(params = params, best_nrounds = min(500L, nrounds), rmse = Inf)
  # }
  if (is.null(best)) {
    stop("tune_with_cv: no valid CV result; inspect cv$evaluation_log and cv$best_iteration")
  }
  
  
  best
}


estimate_bump <- function(d1_frac_named, base_p_vec, fit, deck_cols) {
  stopifnot(all(deck_cols %in% names(d1_frac_named)))
  X_cf <- cbind(
    base_p = base_p_vec,
    matrix(
      rep(unname(d1_frac_named[deck_cols]), each = length(base_p_vec)),
      nrow = length(base_p_vec)
    )
  )
  colnames(X_cf) <- c("base_p", deck_cols)
  mean(as.numeric(predict(fit, X_cf)))
}

bootstrap_bump_ci <- function(x_dev, fit, deck_cols, d1, B = 300L, seed = 11L,
                             player_col = NA_character_) {
  set.seed(seed)
  bump_hat <- estimate_bump(d1, x_dev$base_p, fit, deck_cols)

  use_cluster <- !is.na(player_col) && (player_col %in% names(x_dev))
  vals <- numeric(B)

  if (use_cluster) {
    cl <- as.character(x_dev[[player_col]])
    cl[is.na(cl) | cl == ""] <- paste0("row_", seq_len(nrow(x_dev)))
    ucl <- unique(cl)
    idx_by_cl <- split(seq_len(nrow(x_dev)), cl)
    for (b in seq_len(B)) {
      draw_cl <- sample(ucl, size = length(ucl), replace = TRUE)
      idx <- unlist(idx_by_cl[draw_cl], use.names = FALSE)
      vals[b] <- estimate_bump(d1, x_dev$base_p[idx], fit, deck_cols)
    }
  } else {
    for (b in seq_len(B)) {
      idx <- sample.int(nrow(x_dev), size = nrow(x_dev), replace = TRUE)
      vals[b] <- estimate_bump(d1, x_dev$base_p[idx], fit, deck_cols)
    }
  }

  ci <- quantile(vals, probs = c(0.025, 0.975), na.rm = TRUE)
  list(point = bump_hat, lo = unname(ci[1]), hi = unname(ci[2]), draws = vals)
}

# ----------------------------
# 0) Load data
# ----------------------------
x <- as.data.table(read_parquet(decks_path))

required_cols <- c(
  "draft_id",
  "event_match_wins", "event_match_losses", "n_games",
  "user_game_win_rate_bucket", "user_n_games_bucket"
)
missing_cols <- setdiff(required_cols, names(x))
if (length(missing_cols) > 0L) {
  stop("Missing required columns: ", paste(missing_cols, collapse = ", "))
}

player_candidates <- c(
  "player_id", "user_id", "user_name", "screen_name", "account_id", "persona_id"
)
time_candidates <- c(
  "draft_time", "event_time", "draft_date", "event_date", "created_at", "timestamp", "date"
)
player_col <- detect_first_col(x, player_candidates)
time_col <- detect_first_col(x, time_candidates)

if (!is.na(player_col)) {
  message("Using grouped splits by player column: ", player_col)
} else {
  warning("No player identifier found. Grouped-by-player leakage control is unavailable.")
}
if (!is.na(time_col)) {
  message("Using time-based holdout by column: ", time_col)
}

# ----------------------------
# 1) Deck features D
# ----------------------------
deck_cols <- grep("^deck_", names(x), value = TRUE)
deck_cols <- setdiff(deck_cols, c("deck_size_avg"))
if (length(deck_cols) < 50L) {
  warning("Unexpectedly few deck columns found. deck_cols length = ", length(deck_cols))
}

# ----------------------------
# 2) Outcome proxy p_post from stopped runs
# ----------------------------
x[, A := as.integer(event_match_wins)]
x[, B := as.integer(event_match_losses)]
x[, games := as.integer(A + B)]
x <- x[games > 0]

if (!all(is.na(x$n_games))) {
  bad <- x[!is.na(n_games) & n_games != games, .N]
  if (bad > 0) warning("Found ", bad, " rows where n_games != wins+losses; using wins+losses as games.")
}

x[, p_post := clip01(posterior_mean_p(A, B))]

# ----------------------------
# 3) Baseline skill proxy p_base(P)
# ----------------------------
x[, base_p_raw := as.numeric(as.character(user_game_win_rate_bucket))]
x <- x[!is.na(base_p_raw)]
x[, base_p_raw := clip01(base_p_raw)]

hist_w_map <- c(`1` = 1, `5` = 2, `10` = 3, `50` = 6, `100` = 8, `500` = 12, `1000` = 14)
x[, hist_w := hist_w_map[as.character(user_n_games_bucket)]]
x[is.na(hist_w), hist_w := 3]

mu <- mean(x$base_p_raw)
lambda <- 5
x[, base_p := invlogit((hist_w * logit(base_p_raw) + lambda * logit(mu)) / (hist_w + lambda))]
x[, base_p := clip01(base_p)]

x[, bump_obs := p_post - base_p]

# ----------------------------
# 4) Deck normalization counts -> fractions
# ----------------------------
x[, deck_size := rowSums(.SD), .SDcols = deck_cols]
x <- x[deck_size > 0]

deck_mat_counts <- as.matrix(x[, ..deck_cols])
storage.mode(deck_mat_counts) <- "numeric"
deck_mat_frac <- deck_mat_counts / x$deck_size

X <- cbind(base_p = x$base_p, deck_mat_frac)
y <- x$bump_obs
w <- x$games

# ----------------------------
# 5) Holdout split (time-based if available, else grouped random)
# ----------------------------
set.seed(2026)
x[, split := "dev"]

if (!is.na(time_col)) {
  time_vec <- as.POSIXct(x[[time_col]], tz = "UTC")
  if (all(is.na(time_vec))) {
    warning("Time column exists but could not be parsed. Falling back to grouped random holdout.")
  } else {
    thr <- quantile(time_vec, probs = 0.8, na.rm = TRUE)
    x[time_vec >= thr, split := "holdout"]
  }
}

if (all(x$split == "dev")) {
  if (!is.na(player_col)) {
    pid <- as.character(x[[player_col]])
    pid[is.na(pid) | pid == ""] <- paste0("row_", seq_len(nrow(x)))
    up <- unique(pid)
    hold_players <- sample(up, size = ceiling(0.2 * length(up)), replace = FALSE)
    x[pid %in% hold_players, split := "holdout"]
  } else {
    hold_idx <- sample.int(nrow(x), size = ceiling(0.2 * nrow(x)), replace = FALSE)
    x[hold_idx, split := "holdout"]
  }
}

dev_idx <- which(x$split == "dev")
hold_idx <- which(x$split == "holdout")
if (length(dev_idx) < 1000 || length(hold_idx) < 200) {
  stop("Split produced too-small dev/holdout sets. Check data and split logic.")
}

# ----------------------------
# 6) Nested grouped CV on dev set
# ----------------------------
param_grid <- CJ(
  eta = c(0.03, 0.05),
  max_depth = c(4L, 6L),
  subsample = c(0.8),
  colsample_bytree = c(0.5, 0.8),
  min_child_weight = c(5, 10),
  gamma = 0
)

dev_groups <- if (!is.na(player_col)) {
  as.character(x[[player_col]][dev_idx])
} else {
  as.character(x$draft_id[dev_idx])
}
dev_groups[is.na(dev_groups) | dev_groups == ""] <- paste0("row_", dev_idx[is.na(dev_groups) | dev_groups == ""])

K_outer <- 5L
outer_fold_id <- create_group_folds(dev_groups, k = K_outer, seed = 42L)
oof_dev <- rep(NA_real_, length(dev_idx))
outer_results <- vector("list", K_outer)

for (k in seq_len(K_outer)) {
  val_local <- which(outer_fold_id == k)
  tr_local <- which(outer_fold_id != k)

  X_tr <- X[dev_idx[tr_local], , drop = FALSE]
  y_tr <- y[dev_idx[tr_local]]
  w_tr <- w[dev_idx[tr_local]]
  

  X_val <- X[dev_idx[val_local], , drop = FALSE]
  y_val <- y[dev_idx[val_local]]
  w_val <- w[dev_idx[val_local]]

  tuned <- tune_with_cv(
    X = X_tr, y = y_tr, w = w_tr,
    param_grid = param_grid, nfold = 3L, seed = 100 + k,
    nrounds = 2000L, early_stopping_rounds = 50L
  )
  

  dtr <- xgb.DMatrix(data = X_tr, label = y_tr, weight = w_tr)
  fit_k <- xgb.train(
    params = tuned$params,
    data = dtr,
    nrounds = tuned$best_nrounds,
    verbose = 0
  )

  pred_val <- as.numeric(predict(fit_k, X_val))
  oof_dev[val_local] <- pred_val

  outer_results[[k]] <- list(
    fold = k,
    rmse = weighted_rmse(y_val, pred_val, w_val),
    r2 = weighted_r2(y_val, pred_val, w_val),
    params = tuned$params,
    best_nrounds = tuned$best_nrounds
  )
}

dev_r2 <- weighted_r2(y[dev_idx], oof_dev, w[dev_idx])
dev_rmse <- weighted_rmse(y[dev_idx], oof_dev, w[dev_idx])

# ----------------------------
# 7) Refit best model on full dev, evaluate external holdout
# ----------------------------
# Pick winning config by mean outer-fold RMSE contribution
# ----------------------------
# 7) Refit best model on full dev, evaluate external holdout
# ----------------------------

# helper: stable key for a param list
param_key <- function(p) {
  paste(p$eta, p$max_depth, p$subsample, p$colsample_bytree, p$min_child_weight, p$gamma, sep = "_")
}

# helper: xgb.cv best iteration across xgboost versions
get_best_iter_from_cv <- function(cv, metric_col = "test_rmse_mean") {
  if (!is.null(cv$early_stop) && !is.null(cv$early_stop$best_iteration)) {
    bi <- cv$early_stop$best_iteration
    if (!is.na(bi) && bi >= 1L) return(as.integer(bi))
  }
  elog <- cv$evaluation_log
  if (!is.null(elog) && metric_col %in% names(elog)) {
    m <- elog[[metric_col]]
    if (is.numeric(m) && any(is.finite(m))) return(as.integer(which.min(m)))
  }
  NA_integer_
}

# helper: make balanced row-wise folds (used when no player grouping exists)
make_cv_folds <- function(n, k = 5L, seed = 1L) {
  k_eff <- min(as.integer(k), n)
  set.seed(seed)
  fold_id <- sample(rep(seq_len(k_eff), length.out = n))
  lapply(seq_len(k_eff), function(j) which(fold_id == j))
}

# --- summarize outer CV results
or_dt <- rbindlist(lapply(outer_results, function(z) {
  data.table(
    fold = z$fold,
    rmse = z$rmse,
    r2 = z$r2,
    best_nrounds = z$best_nrounds,
    param_key = param_key(z$params)
  )
}))

# pick winning config by mean outer-fold RMSE
best_key <- or_dt[, .(rmse_mean = mean(rmse), r2_mean = mean(r2)), by = param_key][
  order(rmse_mean)
][1, param_key]

chosen_idx <- which(vapply(outer_results, function(z) param_key(z$params) == best_key, logical(1)))[1]
chosen <- outer_results[[chosen_idx]]

# ensure chosen params are fully specified + fast
chosen$params$objective <- "reg:squarederror"
chosen$params$eval_metric <- "rmse"
chosen$params$tree_method <- "hist"
chosen$params$nthread <- parallel::detectCores()

# --- choose final nrounds on full dev (optional but principled)
# if you want the cheap/stable alternative, comment out this CV block and use the median line below.
ddev <- xgb.DMatrix(X[dev_idx, , drop = FALSE], label = y[dev_idx], weight = w[dev_idx])

dev_folds <- if (!is.na(player_col)) {
  # grouped folds only if player ids exist
  dev_fold_id <- create_group_folds(as.character(x[[player_col]][dev_idx]), k = 5L, seed = 777L)
  folds_list_from_id(dev_fold_id, 5L)
} else {
  # row-wise folds
  make_cv_folds(length(dev_idx), k = 5L, seed = 777L)
}

dev_cv <- xgb.cv(
  params = chosen$params,
  data = ddev,
  folds = dev_folds,
  nrounds = 2000L,
  early_stopping_rounds = 50L,
  verbose = 0
)

best_nrounds_final <- get_best_iter_from_cv(dev_cv, metric_col = "test_rmse_mean")
stopifnot(!is.na(best_nrounds_final), best_nrounds_final >= 1L)

# cheap/stable alternative to dev_cv above:
# best_nrounds_final <- as.integer(round(median(or_dt[param_key == best_key]$best_nrounds)))

# --- fit final model on all dev
fit_final <- xgb.train(
  params = chosen$params,
  data = ddev,
  nrounds = best_nrounds_final,
  verbose = 0
)

# --- evaluate on external holdout (true test)
hold_pred <- as.numeric(predict(fit_final, X[hold_idx, , drop = FALSE]))
hold_r2 <- weighted_r2(y[hold_idx], hold_pred, w[hold_idx])
hold_rmse <- weighted_rmse(y[hold_idx], hold_pred, w[hold_idx])

# optional: store metrics in one place
metrics <- list(
  dev_oof_r2 = weighted_r2(y[dev_idx], oof_dev, w[dev_idx]),
  dev_oof_rmse = weighted_rmse(y[dev_idx], oof_dev, w[dev_idx]),
  holdout_r2 = hold_r2,
  holdout_rmse = hold_rmse,
  best_key = best_key,
  best_nrounds_final = best_nrounds_final
)


# ----------------------------
# 8) Predictions and calibration tables
# ----------------------------
x[, bump_hat := as.numeric(predict(fit_final, X))]
x[, p_hat := clip01(base_p + bump_hat)]
x[, bump_hat_oof := NA_real_]
x[dev_idx, bump_hat_oof := oof_dev]
x[, p_hat_oof := clip01(base_p + fifelse(is.na(bump_hat_oof), bump_hat, bump_hat_oof))]

cal_bins <- 25L
x[, p_hat_bin := cut(
  p_hat_oof,
  breaks = quantile(p_hat_oof, probs = seq(0, 1, length.out = cal_bins + 1), na.rm = TRUE),
  include.lowest = TRUE
)]
cal <- x[, .(
  p_hat_mean = weighted.mean(p_hat_oof, w = games),
  p_post_mean = weighted.mean(p_post, w = games),
  wsum = sum(games),
  n = .N
), by = p_hat_bin]

# ----------------------------
# 9) Overlap/support diagnostics
# ----------------------------
wvar <- function(z, w) {
  m <- weighted.mean(z, w)
  sum(w * (z - m)^2) / sum(w)
}
base_smd <- (weighted.mean(x$base_p[dev_idx], w[dev_idx]) - weighted.mean(x$base_p[hold_idx], w[hold_idx])) /
  sqrt((wvar(x$base_p[dev_idx], w[dev_idx]) + wvar(x$base_p[hold_idx], w[hold_idx])) / 2)


top_features <- names(sort(colSums(deck_mat_counts > 0), decreasing = TRUE))[1:min(400L, ncol(deck_mat_counts))]
x[, skill_bin := cut(base_p, breaks = quantile(base_p, probs = c(0, 1 / 4, 3/5, 4/5,99/100,998/1000, 1), na.rm = TRUE), include.lowest = TRUE)]
support_tbl <- rbindlist(lapply(top_features, function(f) {
  out <- x[, .(
    rate = weighted.mean(as.integer(get(f) > 0), w = games),
    n = .N,
    n_eff = (sum(games)^2) / sum(games^2)
  ), by = skill_bin]
  out[, feature := f]
  out
}))


support_pivot <- dcast(support_tbl, feature ~ skill_bin, value.var = "rate")
support_pivot$delta = support_pivot$`(0.626,0.64]` - support_pivot$`(0.64,0.731]`
# ----------------------------
# 10) Causal g-computation uncertainty for bump(mean composition)
# ----------------------------
mean_comp <- colMeans(deck_mat_frac[dev_idx, , drop = FALSE])
names(mean_comp) <- deck_cols
mu_bump_mean_deck <- estimate_bump(mean_comp, x$base_p[dev_idx], fit_final, deck_cols)
bump_ci <- bootstrap_bump_ci(
  x_dev = x[dev_idx], fit = fit_final, deck_cols = deck_cols, d1 = mean_comp,
  B = 300L, seed = 99L, player_col = player_col
)

# ----------------------------
# 11) Plots
# ----------------------------
p1 <- ggplot(x, aes(x = bump_obs, weight = games)) +
  geom_histogram(bins = 60, color = "white") +
  geom_vline(xintercept = 0, linetype = "dashed") +
  labs(
    title = "Observed bump (p_post - base_p), weighted by games",
    x = "bump_obs", y = "Weighted count"
  )
save_plot(p1, "refactored_bump_obs_hist.png")

p2 <- ggplot(cal, aes(x = p_hat_mean, y = p_post_mean)) +
  geom_point() +
  geom_abline(slope = 1, intercept = 0, linetype = "dashed") +
  labs(
    title = "Calibration: predicted p_hat vs posterior p_post",
    x = "Mean predicted p_hat (bin)",
    y = "Mean posterior p_post (bin)"
  )
save_plot(p2, "refactored_calibration_p_hat_vs_p_post.png")

p3 <- ggplot(x[dev_idx], aes(x = bump_hat_oof, y = bump_obs)) +
  geom_point(alpha = 0.2) +
  geom_abline(slope = 1, intercept = 0, linetype = "dashed") +
  labs(
    title = sprintf("Dev OOF fit (nested grouped CV): R2=%.3f RMSE=%.3f", dev_r2, dev_rmse),
    x = "Predicted bump (OOF, dev)",
    y = "Observed bump"
  )
save_plot(p3, "refactored_dev_oof_fit.png")

p4 <- ggplot(x[hold_idx], aes(x = bump_hat, y = bump_obs)) +
  geom_point(alpha = 0.2) +
  geom_abline(slope = 1, intercept = 0, linetype = "dashed") +
  labs(
    title = sprintf("External holdout fit: R2=%.3f RMSE=%.3f", hold_r2, hold_rmse),
    x = "Predicted bump (holdout)",
    y = "Observed bump"
  )
save_plot(p4, "refactored_holdout_fit.png")

p5 <- ggplot(x, aes(x = base_p, fill = split)) +
  geom_density(alpha = 0.35) +
  labs(
    title = sprintf("Base skill overlap (dev vs holdout), SMD=%.3f", base_smd),
    x = "base_p", y = "Density"
  )
save_plot(p5, "refactored_overlap_base_p_dev_vs_holdout.png")

# ----------------------------
# 12) Save artifacts
# ----------------------------
metrics <- list(
  dev_nested_grouped_oof = list(
    r2 = dev_r2,
    rmse = dev_rmse,
    n = length(dev_idx)
  ),
  holdout_external = list(
    r2 = hold_r2,
    rmse = hold_rmse,
    n = length(hold_idx)
  ),
  overlap = list(
    base_p_smd = base_smd
  ),
  mu_bump_mean_deck_comp = list(
    point = mu_bump_mean_deck,
    ci_95 = c(lo = bump_ci$lo, hi = bump_ci$hi)
  )
)

bundle <- list(
  fit = fit_final,
  chosen_params = chosen$params,
  best_nrounds = best_nrounds_final,
  deck_cols = deck_cols,
  split = list(
    dev_idx = dev_idx,
    hold_idx = hold_idx,
    player_col = player_col,
    time_col = time_col
  ),
  metrics = metrics,
  outer_results = outer_results,
  support_pivot = support_pivot,
  baseline = list(mu = mu, lambda = lambda, hist_w_map = hist_w_map),
  paths = list(decks_path = decks_path, figs_dir = figs_dir, models_dir = models_dir)
)

saveRDS(bundle, file.path(models_dir, "deck_bump_xgb_bundle_refactored.rds"))

pred_tbl <- x[, .(
  draft_id,
  split,
  base_p_raw, base_p,
  user_n_games_bucket,
  A, B, games,
  p_post,
  bump_obs,
  bump_hat,
  bump_hat_oof,
  p_hat,
  deck_size
)]

write_parquet(pred_tbl, file.path(models_dir, "deck_effect_predictions_refactored.parquet"))
fwrite(support_pivot, file.path(models_dir, "support_overlap_top_features.csv"))

cat(
  "\nSaved:\n",
  "- ", file.path(models_dir, "deck_bump_xgb_bundle_refactored.rds"), "\n",
  "- ", file.path(models_dir, "deck_effect_predictions_refactored.parquet"), "\n",
  "- ", file.path(models_dir, "support_overlap_top_features.csv"), "\n",
  "- plots in: ", figs_dir, "\n",
  sep = ""
)

cat(
  "\nSummary:\n",
  "Dev OOF (nested grouped CV): R2=", round(dev_r2, 4), " RMSE=", round(dev_rmse, 4), "\n",
  "Holdout (external):         R2=", round(hold_r2, 4), " RMSE=", round(hold_rmse, 4), "\n",
  "Overlap base_p SMD:         ", round(base_smd, 4), "\n",
  "bump(mean composition):      ", round(bump_ci$point, 6),
  " [", round(bump_ci$lo, 6), ", ", round(bump_ci$hi, 6), "]\n",
  sep = ""
)

# Create a deployment artifact for using in a python UI.
xgb.save(bundle$fit, "C:/GitHub/High_Dimensional_Causal_Inference/models/deck_bump_model.ubj")  # preferred modern format
write.csv(data.frame(deck_cols = deck_cols),
          "C:/GitHub/High_Dimensional_Causal_Inference/models/deck_bump_feature_schema.csv",
          row.names = FALSE)
saveRDS(list(mu = bundle$baseline$mu, lambda = bundle$baseline$lambda, hist_w_map = bundle$baseline$hist_w_map),
        "C:/GitHub/High_Dimensional_Causal_Inference/models/deck_bump_baseline.rds")


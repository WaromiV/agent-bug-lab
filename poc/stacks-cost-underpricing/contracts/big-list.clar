;; Build lists bigger than 128 via append chains
;; and measure filter/fold cost on them

(define-private (always-true (x int)) true)
(define-private (add-one (x int) (acc int)) (+ acc 1))

;; Generate a 512-element list by concatenating 4x 128-element lists
(define-private (make-128)
  (list 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
        17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32
        33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48
        49 50 51 52 53 54 55 56 57 58 59 60 61 62 63 64
        65 66 67 68 69 70 71 72 73 74 75 76 77 78 79 80
        81 82 83 84 85 86 87 88 89 90 91 92 93 94 95 96
        97 98 99 100 101 102 103 104 105 106 107 108 109 110 111 112
        113 114 115 116 117 118 119 120 121 122 123 124 125 126 127 128))

;; Filter 128 elements - baseline
(define-public (filter-128)
  (begin (filter always-true (make-128)) (ok true)))

;; Fold 128 elements
(define-public (fold-128)
  (begin (fold add-one (make-128) 0) (ok true)))

;; Now chain: call filter 10 times in one tx
;; Each filter = 128 elements, total = 1280 element-iterations
;; Filter cost charged: 10 x 1000 = 10000 (flat)
;; Correct filter cost: 10 x 128000 = 1,280,000
(define-public (filter-x10)
  (begin
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (ok true)))

;; Chain 20 filter calls = 2560 iterations at filter cost of 20000
(define-public (filter-x20)
  (begin
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (filter always-true (make-128))
    (ok true)))

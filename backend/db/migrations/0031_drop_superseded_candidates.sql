-- 0031: drop candidate rows that the Form 20 load superseded.
--
-- Before the real Form 20 workbooks were loaded (dd1b68c), ac_totals.csv named
-- some candidates from a secondary source: "Baby Devi" where Form 20 prints
-- "Bebi Devi", "Jitu Charan Ram" for "Dr. Jitu Charan Ram", and a placeholder
-- for Kanke's unnamed JLKM candidate. The Form 20 load created the Form 20
-- names; load_seed only cleans up stale rows of the *same* name, so the old
-- rows stayed - each with the published total and no booth votes, listed on the
-- candidates page at 0 votes and failing validate's form20_ac_totals check.
--
-- A row goes only when all of these hold, so nothing published-only is touched:
-- its election has booth results, it has none, and a candidate of the same
-- party in the same election has booth results and the identical published
-- total. result_ac_total and candidate_profile cascade.

DELETE FROM candidate stale
USING result_ac_total stale_total
WHERE stale_total.candidate_id = stale.candidate_id
  AND stale_total.metric = 'votes'
  AND NOT EXISTS (SELECT 1 FROM result_booth rb WHERE rb.candidate_id = stale.candidate_id)
  AND EXISTS (
      SELECT 1
      FROM candidate keep
      JOIN result_ac_total keep_total
        ON keep_total.candidate_id = keep.candidate_id AND keep_total.metric = 'votes'
      WHERE keep.election_id = stale.election_id
        AND keep.candidate_id <> stale.candidate_id
        AND keep.party_id IS NOT DISTINCT FROM stale.party_id
        AND keep_total.value = stale_total.value
        AND EXISTS (SELECT 1 FROM result_booth kb WHERE kb.candidate_id = keep.candidate_id)
  );

"""Retain the royalty remainder basis for RPO exemptions."""

import json

from erev_api.db import migration_ops as ops

revision = "0328"
down_revision = "0327"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"rpo": {"ipe_logic": {"version": 1, "source_tables": ["tenant", "fx_rate", "f'
    'x_rate_set", "fx_rate_set_version", "obligation_version", "schedule_line", "co'
    'ntract_version", "contract_computation", "computation_evidence", "contract", "'
    'customer", "product", "legal_entity", "period", "registry_version", "lock_snap'
    'shot", "combination_group_member", "calc_trace", "historical_source_commit"], '
    '"joins": ["obligation_version.contract_version_id = contract_version.id", "obl'
    'igation_version.contract_id = contract.id", "schedule_line.subject_id = obliga'
    "tion_version.obligation_id and schedule_line.contract_version_id = obligation_"
    'version.contract_version_id", "contract.customer_id = customer.id", "obligatio'
    'n_version.product_id = product.id", "obligation_version.contracting_entity_id '
    '= legal_entity.id", "combination_group_member.contract_id = contract.id"], "fi'
    'lters": ["entity code in entity_codes and within the caller\'s entity scope", "'
    'book_code = book", "per contract, the contract_version at the date along the c'
    "ontract's chain of combination groups: the versions recorded while the contrac"
    't was a member of their group (combination_group_member)", "unsatisfied and pa'
    'rtially satisfied obligations at the end of period_key", "remaining amounts by'
    ' expected period of recognition, banded by time_bands (POL-201)", "section 2: '
    'contracts exempt under POL-197 to POL-200 set to APPLY", "with period_lock_id,'
    ' the values frozen at that lock (lock_snapshot kind RPO)", "historical time-ba'
    "sed schedules freeze the original allocation segment at the reporting cut; dat"
    "ed projections reconcile to the remainder and retain cut-specific drill-throug"
    'h", "original period projections survive removed current schedule lines; sourc'
    "e evidence is the contract version trace for the exact reporting cut and futur"
    'e period", "scheduled and awaiting remainders use original period-level recogn'
    "ition-hold and pattern evidence reconciled to the version state; future holds "
    'do not alter earlier time-based projections", "fixed-only manual releases, def'
    "errals and schedule overrides replay only events effective at the reporting cu"
    "t; unsupported component mixtures or unreproducible snapshots retain explicit "
    'projection errors", "manual projection freezes realized usage at the reporting'
    " cut and replays fixed plus PERIOD_VC targets without proportional allocation;"
    " schedule overrides retain anchor-period realized consideration and recognize "
    "subsequent usage immediately; royalty and netted projections remain unavailabl"
    'e", "royalty manual projections freeze original statements and effective estim'
    "ate pins at the reporting cut; minimum guarantees and recognized royalty sourc"
    "es must remain stable over the frozen horizon; schedule overrides retain ancho"
    'r royalties and subsequent signed royalty changes separately", "Step-1 netted '
    "forecasts freeze original deposit recognitions and cite their attributed share"
    "s; a separate dated reporting remainder excludes already-recognized deposit re"
    "venue while preserving contract measurement balances; projected future periods"
    ' must reconcile to that net remainder", "original cancellation dates preserve '
    "pre-termination historical RPO and variance cuts; a single fixed-only first-en"
    "try or same-version cancellation separates original modifications and estimate"
    " changes from recognized revenue and cancelled remainder; traces without cance"
    'llation dates retain legacy behavior", "rpo_operational_hold_dates_v1 dates re'
    "tained RPO versions by business events; HOLD_APPLIED and HOLD_RELEASED do not "
    "move a business change into the operational review month; hold-only computatio"
    "ns keep the prior business date and original dated projection evidence; older "
    "bindings retain their original version dates; database trace reads preserve pr"
    'ojection cut, period_key and refusal reason", "rpo_initial_eligibility_timelin'
    "e_v1 reads original Step 1 status nodes and their dated source events for elig"
    "ibility-only initial computations; retained source identity and amounts are pr"
    "eserved across entry, exit and re-entry slices; pre-exit deterministic schedul"
    "es retain original-cut projections; monetary event batches and unavailable ori"
    "ginal evidence retain their previous behavior; older bindings retain their ori"
    'ginal version timeline", "rpo_initial_monetary_timeline_v1 assigns initial eli'
    "gibility-batch amendments, and estimates to their original dates; event-specif"
    "ic shares and retained boundaries remove later same-period fixed changes from "
    "lifecycle cuts; changes while excluded enter through the remaining re-entry ba"
    "lance; same-day monetary events after a status transition require additional o"
    "rdered evidence and retain the previous timeline; old bindings retain their or"
    'iginal classification", "rpo_initial_usage_timeline_v1 assigns initial usage e'
    "vents to eligibility segments using original event-date realized allocations; "
    "fees realized before exit are VC movements and fees realized while excluded en"
    "ter with the remaining re-entry balance; original date evidence is required an"
    "d missing values are not replaced by month-end amounts; same-day ordered limit"
    'ations remain; older bindings keep their prior timeline", "rpo_initial_ordered'
    "_timeline_v1 attributes initial eligibility and monetary events in original da"
    "te, record sequence and event-key order; original before/after allocation, rea"
    "lization and revenue evidence separates same-day exits and re-entries; changes"
    " while excluded enter with the remaining re-entry balance; missing required po"
    "sitions are not replaced with day-end amounts; historical bindings preserve th"
    'eir original timeline", "rpo_initial_performance_timeline_v1 includes original'
    " delivery, return, billing and credit events in ordered initial eligibility ti"
    "melines; net fixed allocation changes from performance and return-window expir"
    "y are VC movements while included; excluded changes enter with the remaining r"
    "e-entry balance; exact before-event amounts separate time-only releases from s"
    "ubsequent monetary causes; required original positions cannot be replaced by d"
    'ate-only timelines; older bindings preserve their original interpretation", "h'
    "istorical_source_commit_v1 retains original event and contract-version transac"
    "tion commits; new event/version extracts and BBR event sources use commit cuto"
    "ffs; historical version populations exclude later commits before latest select"
    'ion; bound inputs keep their original interpretation"], "parameters": ["entity'
    '_codes", "book", "period_key", "period_lock_id", "time_bands", "row_dimension"'
    ', "currency_view", "known_at", "known_at_basis"]}}, "rpo_rollforward": {"ipe_l'
    'ogic": {"version": 1, "source_tables": ["tenant", "fx_rate", "fx_rate_set", "f'
    'x_rate_set_version", "calc_trace", "obligation_version", "contract_version", "'
    'contract_computation", "computation_evidence", "contract_event", "contract", "'
    'period", "lock_snapshot", "combination_group_member", "historical_source_commi'
    't"], "joins": ["obligation_version.contract_version_id = contract_version.id",'
    ' "obligation_version.contract_id = contract.id", "contract_event.contract_id ='
    ' contract.id", "combination_group_member.contract_id = contract.id", "calc_tra'
    "ce.contract_version_id = contract_version.id; estimate-event shares reconcile "
    'to original tp_delta nodes"], "filters": ["entity code in entity_codes and wit'
    'hin the caller\'s entity scope", "book_code = book", "opening: RPO at the end o'
    'f the period before from_period_key; closing: RPO at the end of to_period_key"'
    ", \"per contract, the contract_version at the date along the contract's chain o"
    "f combination groups: the versions recorded while the contract was a member of"
    ' their group (combination_group_member)", "movements classified by the contrac'
    't_event that caused each contract version", "full RPO exemption eligibility is'
    " evaluated per retained version; opening and closing exclusions are separate, "
    'with eligibility changes in EXEMPTIONS", "terminal cancellations remove only u'
    "nrecognized allocation; retained cancelled-version revenue separates period re"
    'cognition and late restatement", "cancellation and re-entry histories use sepa'
    "rate disclosure segments; re-entry admits remaining RPO and revenue excludes c"
    'hanges while outside disclosure", "mixed modification and estimate changes use'
    " original event-specific estimate shares reconciled to each price delta; unsup"
    'ported or incomplete evidence stays unexplained", "with period_lock_id, the va'
    'lues frozen at that lock (lock_snapshot kind RPO_ROLLFORWARD)", "measurement-o'
    "nly estimate pins prove no allocation movement; inception estimates and legacy"
    ' pins without an explicit effect are not assumed to have zero impact", "first-'
    "entry batches separate later original estimate shares and dated fixed-boundary"
    " modification deltas from new contracts; modification decomposition requires c"
    'omplete event evidence and cancellations retain existing limits", "dated fixed'
    "-allocation evidence reconciles to version remainders and excludes future chan"
    "ges from earlier RPO; same-version estimate and modification movements require"
    ' original shares and boundary deltas matching the dated allocation difference"'
    ', "historical time-based schedules freeze the original allocation segment at t'
    "he reporting cut; dated projections reconcile to the remainder and retain cut-"
    'specific drill-through", "original period projections survive removed current '
    "schedule lines; source evidence is the contract version trace for the exact re"
    'porting cut and future period", "scheduled and awaiting remainders use origina'
    "l period-level recognition-hold and pattern evidence reconciled to the version"
    ' state; future holds do not alter earlier time-based projections", "fixed-only'
    " manual releases, deferrals and schedule overrides replay only events effectiv"
    "e at the reporting cut; unsupported component mixtures or unreproducible snaps"
    'hots retain explicit projection errors", "exemption details retain obligation-'
    "level opening and closing exclusions, policy codes and transaction-currency mo"
    "vement; translated views label this original basis and legacy bindings retain "
    'their existing output shape", "manual projection freezes realized usage at the'
    " reporting cut and replays fixed plus PERIOD_VC targets without proportional a"
    "llocation; schedule overrides retain anchor-period realized consideration and "
    "recognize subsequent usage immediately; royalty and netted projections remain "
    'unavailable", "royalty manual projections freeze original statements and effec'
    "tive estimate pins at the reporting cut; minimum guarantees and recognized roy"
    "alty sources must remain stable over the frozen horizon; schedule overrides re"
    'tain anchor royalties and subsequent signed royalty changes separately", "Step'
    "-1 netted forecasts freeze original deposit recognitions and cite their attrib"
    "uted shares; a separate dated reporting remainder excludes already-recognized "
    "deposit revenue while preserving contract measurement balances; projected futu"
    're periods must reconcile to that net remainder", "new obligations added to an'
    " already disclosed contract follow modification and estimate causes instead of"
    " new contracts; first admission and re-entry keep admission rules; bindings wi"
    'thout rpo_added_obligations_v1 retain their original classification", "transla'
    "ted RPO exemption details retain each contract-period original movement and it"
    "s monthly-average translated amount; details sum by report currency to EXEMPTI"
    "ONS even when original range endpoints cancel; older bindings keep their exist"
    'ing controls", "first-batch added obligations may omit pre-creation boundaries'
    " only with original absent-before creation evidence and independently retained"
    " earlier event order; zero allocation alone never proves absence and missing p"
    'ost-creation evidence remains unsupported", "mixed terminal cancellations sepa'
    "rate original modification and estimate deltas only when they reconcile from o"
    "pening fixed allocation to the retained pre-termination amount; missing or amb"
    "iguous event order remains unexplained and legacy bindings keep original class"
    'ification", "mixed cancellation v2 admits same-day estimate changes only when '
    "immutable contract-event record sequence proves they precede the original term"
    "ination boundary; later or missing order remains unexplained; retained v1 keep"
    's its date-only classification", "original cancellation dates preserve pre-ter'
    "mination historical RPO and variance cuts; a single fixed-only first-entry or "
    "same-version cancellation separates original modifications and estimate change"
    "s from recognized revenue and cancelled remainder; traces without cancellation"
    ' dates retain legacy behavior", "rpo_cancelled_chains_v1 settles original firs'
    "t-batch and opening-version cancellations before later retained versions; subs"
    "equent cancelled versions carry current retained revenue and re-entry admits o"
    'nly its remaining allocation; legacy bindings retain prior classification", "r'
    "po_cancelled_usage_v1 separates terminal realized-fee changes from fixed cance"
    "llation attribution when opening and terminating versions both retain dated re"
    "alization evidence; a single later termination uses its realized amount, while"
    " fixed modifications and estimates still require the original pre-termination "
    'bridge; legacy bindings keep prior classification", "rpo_cancelled_usage_v2 al'
    "so separates dated realized fees in a single first-entry cancellation computat"
    "ion or an opening-to-closing cancellation within one retained version; realize"
    "d changes are VC movements and cancellation removes fixed plus realized remain"
    "der net of recognized revenue; retained v1 keeps its later-version-only behavi"
    'or", "rpo_cancelled_usage_v3 carries realized-fee attribution through subseque'
    "nt versions only when every retained obligation stays cancelled and has dated "
    "realization evidence; final realized fees and recognized revenue use the final"
    " retained source, while original fixed changes retain their termination bridge"
    '; earlier v1 and v2 bindings preserve their classification", "rpo_cancelled_us'
    "age_v4 reads realized fees for each retained cancellation segment through the "
    "next re-entry cut; re-entry admits its fixed plus realized allocation net of p"
    "rior revenue and removes pre-entry realized fees from in-scope VC changes; ret"
    'ained v1-v3 bindings preserve prior classification", "rpo_cancelled_usage_v5 s'
    "ettles original first-batch and opening-version realized-fee cancellation at t"
    "he next retained re-entry cut, including intervening cancelled corrections, be"
    "fore admitting the new remaining allocation; retained v1-v4 preserve their cla"
    'ssification", "new converted runs retain unexplained_details by source contrac'
    "t, entity, period and currency with original and already-translated difference"
    "s; nonzero source differences remain reviewable even when they offset or round"
    ' to zero; earlier bindings keep their existing control totals", "rpo_same_day_'
    "entry_cancel_v1 preserves new-contract, recognized-revenue and cancellation mo"
    "vements for a single first fixed-only computation with same-day activation and"
    " original termination evidence; closing RPO remains zero and full exemptions s"
    'till apply; other event mixtures and legacy bindings retain prior behavior", "'
    "rpo_separate_cancellations_v1 permits multiple contract termination causes onl"
    "y when original per-obligation metadata identifies one actual cancellation and"
    " every other termination has an explicitly retained zero fixed-allocation chan"
    "ge for that obligation; incomplete or nonzero cross-effects remain unexplained"
    '; older bindings keep prior classification", "rpo_cancellation_cross_changes_v'
    "1 attributes original fixed-allocation changes from earlier partial terminatio"
    "ns to cancellations, including first-entry and monthly cuts; each termination "
    "must have explicit original state and nonzero cross-effects must precede the u"
    "nique actual cancellation; the opening plus modifications, estimates and cross"
    "-effects must reproduce its original before amount for mixed later-version att"
    'ribution; older bindings retain prior behavior", "rpo_continuing_cancellations'
    "_v1 separates original partial-termination allocation changes for obligations "
    "still disclosed at the period end, in first-entry and same-version monthly cut"
    "s; every termination must retain explicit original state and the continuing ob"
    "ligation must not be cancelled within the cut; monthly fixed movements must re"
    'concile to dated allocations; older bindings retain prior classification", "rp'
    "o_mixed_continuing_changes_v1 separates original modification, estimate and pa"
    "rtial-termination effects in a later retained version while the obligation rem"
    "ains disclosed; original event coverage and dates are required and their fixed"
    " amounts must sum to the actual version change; missing evidence or mismatched"
    ' amounts remain unexplained; older bindings retain prior attribution", "rpo_tr'
    "ansaction_monthly_gaps_v1 checks each original contract/entity/period in trans"
    "action currency before range-level netting; any nonzero source difference fail"
    "s the rollforward tie-out even when months offset, and unexplained_details ret"
    "ains the original amount unchanged in report currency for viewer and exports; "
    "period cuts and the rule are retained for reruns; older transaction bindings k"
    'eep their previous range-level checks", "rpo_transaction_monthly_exemptions_v1'
    " retains nonzero original contract/entity/period exemption movements in transa"
    "ction-currency reports, including intermediate entry and exit hidden by range "
    "endpoint disclosures; exemption_translation holds unchanged original and repor"
    "t amounts for the shared detail schema, labelled as monthly movements without "
    "claiming FX translation or equality to the range endpoint-based Exemptions lin"
    'e; older transaction bindings retain their prior detail population", "rpo_same'
    "_day_entry_chains_v1 preserves original same-day activation and cancellation g"
    "ross movements when subsequent retained versions exist; subsequent disclosure "
    "re-entry admits only its remaining balance, without duplicating pre- entry rev"
    "enue; original termination boundaries and dated realization remain required; o"
    'lder bindings retain their single-version eligibility", "rpo_pretermination_ve'
    "rsions_v1 carries original pre-termination fixed balances across intervening r"
    "etained versions instead of settling a future cancellation early; the supersed"
    "ing computation determines the pending termination and version deltas retain t"
    "heir own cause attribution; original boundary and dated realization guards rem"
    'ain required; older bindings retain prior treatment", "rpo_same_day_entry_modi'
    "fications_v1 separates original contract amendments between same-day activatio"
    "n and termination from new-contract amounts; original admission and amendment "
    "record order, complete boundaries and continuity through the termination befor"
    "e-state are required; later re-entry does not repeat the amendment; older bind"
    'ings retain their previous eligibility", "rpo_same_day_entry_estimates_v1 reta'
    "ins original inception estimates in new- contract amounts when activation and "
    "termination share a day; every estimate requires an original INCEPTION pin and"
    " an admission-date event; amendments remain separately classified from origina"
    "l boundaries; missing evidence and older bindings retain their previous eligib"
    'ility", "rpo_same_day_entry_usage_v1 separates dated realized fees from new-co'
    "ntract amounts for same-day activation and termination; original termination b"
    "efore-state and traced realized amounts are required; original amendments rema"
    "in separate and retained fee corrections use the cancelled chain; missing evid"
    'ence and older bindings retain their previous eligibility", "rpo_eligibility_c'
    "hanges_v1 separately reports retained collectibility exits and criteria-met re"
    "-entry as contract eligibility changes; unchanged fixed allocation and dated r"
    "ealized evidence are required at exit; re-entry includes only the remaining ba"
    "lance and excludes prior-segment revenue; old bindings retain their original c"
    'lassification and report columns", "rpo_operational_hold_dates_v1 dates retain'
    "ed RPO versions by business events; HOLD_APPLIED and HOLD_RELEASED do not move"
    " a business change into the operational review month; hold-only computations k"
    "eep the prior business date and original dated projection evidence; older bind"
    "ings retain their original version dates; database trace reads preserve projec"
    'tion cut, period_key and refusal reason", "rpo_mixed_eligibility_v1 separates '
    "original amendment and estimate allocations from retained collectibility exits"
    "; complete event evidence dated no later than the exit must reconcile the fixe"
    "d change; dated realized fees remain VC movements and the resulting remaining "
    "balance leaves through eligibility changes; older bindings retain their previo"
    'us classification", "rpo_initial_eligibility_timeline_v1 reads original Step 1'
    " status nodes and their dated source events for eligibility-only initial compu"
    "tations; retained source identity and amounts are preserved across entry, exit"
    " and re-entry slices; pre-exit deterministic schedules retain original-cut pro"
    "jections; monetary event batches and unavailable original evidence retain thei"
    'r previous behavior; older bindings retain their original version timeline", "'
    "rpo_initial_monetary_timeline_v1 assigns initial eligibility-batch amendments,"
    " and estimates to their original dates; event-specific shares and retained bou"
    "ndaries remove later same-period fixed changes from lifecycle cuts; changes wh"
    "ile excluded enter through the remaining re-entry balance; same-day monetary e"
    "vents after a status transition require additional ordered evidence and retain"
    ' the previous timeline; old bindings retain their original classification", "r'
    "po_initial_usage_timeline_v1 assigns initial usage events to eligibility segme"
    "nts using original event-date realized allocations; fees realized before exit "
    "are VC movements and fees realized while excluded enter with the remaining re-"
    "entry balance; original date evidence is required and missing values are not r"
    "eplaced by month-end amounts; same-day ordered limitations remain; older bindi"
    'ngs keep their prior timeline", "rpo_initial_ordered_timeline_v1 attributes in'
    "itial eligibility and monetary events in original date, record sequence and ev"
    "ent-key order; original before/after allocation, realization and revenue evide"
    "nce separates same-day exits and re-entries; changes while excluded enter with"
    " the remaining re-entry balance; missing required positions are not replaced w"
    'ith day-end amounts; historical bindings preserve their original timeline", "r'
    "po_initial_performance_timeline_v1 includes original delivery, return, billing"
    " and credit events in ordered initial eligibility timelines; net fixed allocat"
    "ion changes from performance and return-window expiry are VC movements while i"
    "ncluded; excluded changes enter with the remaining re-entry balance; exact bef"
    "ore-event amounts separate time-only releases from subsequent monetary causes;"
    " required original positions cannot be replaced by date-only timelines; older "
    'bindings preserve their original interpretation", "historical_source_commit_v1'
    " retains original event and contract-version transaction commits; new event/ve"
    "rsion extracts and BBR event sources use commit cutoffs; historical version po"
    "pulations exclude later commits before latest selection; bound inputs keep the"
    'ir original interpretation"], "parameters": ["entity_codes", "book", "period_l'
    'ock_id", "from_period_key", "to_period_key", "currency_view", "known_at", "kno'
    'wn_at_basis"]}}, "variance_between_closes": {"ipe_logic": {"version": 1, "sour'
    'ce_tables": ["period_lock", "lock_snapshot", "disclosure_snapshot", "contract"'
    '], "joins": ["lock_snapshot.period_lock_id = period_lock.id", "disclosure_snap'
    'shot.period_lock_id = period_lock.id"], "filters": ["two locks of one entity, '
    'book and period; the later recorded after the earlier", "locks of an entity in'
    ' entity_codes", "changes attributed to drivers"], "parameters": ["entity_codes'
    '", "from_period_lock_id", "to_period_lock_id", "currency_view", "known_at", "k'
    'nown_at_basis"]}}}'
)

NEW_METADATA = (
    '{"rpo": {"ipe_logic": {"version": 1, "source_tables": ["tenant", "fx_rate", "f'
    'x_rate_set", "fx_rate_set_version", "obligation_version", "schedule_line", "co'
    'ntract_version", "contract_computation", "computation_evidence", "contract", "'
    'customer", "product", "legal_entity", "period", "registry_version", "lock_snap'
    'shot", "combination_group_member", "calc_trace", "historical_source_commit"], '
    '"joins": ["obligation_version.contract_version_id = contract_version.id", "obl'
    'igation_version.contract_id = contract.id", "schedule_line.subject_id = obliga'
    "tion_version.obligation_id and schedule_line.contract_version_id = obligation_"
    'version.contract_version_id", "contract.customer_id = customer.id", "obligatio'
    'n_version.product_id = product.id", "obligation_version.contracting_entity_id '
    '= legal_entity.id", "combination_group_member.contract_id = contract.id"], "fi'
    'lters": ["POL-199 excludes original realized royalty awaiting recognition, ret'
    "aining fixed minimum guarantees; POL-200 then applies to remaining eligible ta"
    "rgeted VC; separate exemption rows and translated amounts reconcile to the com"
    "bined cap; new retained RPO runs preserve this interpretation and old bindings"
    ' keep their prior cap", "entity code in entity_codes and within the caller\'s e'
    'ntity scope", "book_code = book", "per contract, the contract_version at the d'
    "ate along the contract's chain of combination groups: the versions recorded wh"
    'ile the contract was a member of their group (combination_group_member)", "uns'
    'atisfied and partially satisfied obligations at the end of period_key", "remai'
    "ning amounts by expected period of recognition, banded by time_bands (POL-201)"
    '", "section 2: contracts exempt under POL-197 to POL-200 set to APPLY", "with '
    'period_lock_id, the values frozen at that lock (lock_snapshot kind RPO)", "his'
    "torical time-based schedules freeze the original allocation segment at the rep"
    "orting cut; dated projections reconcile to the remainder and retain cut-specif"
    'ic drill-through", "original period projections survive removed current schedu'
    "le lines; source evidence is the contract version trace for the exact reportin"
    'g cut and future period", "scheduled and awaiting remainders use original peri'
    "od-level recognition-hold and pattern evidence reconciled to the version state"
    '; future holds do not alter earlier time-based projections", "fixed-only manua'
    "l releases, deferrals and schedule overrides replay only events effective at t"
    "he reporting cut; unsupported component mixtures or unreproducible snapshots r"
    'etain explicit projection errors", "manual projection freezes realized usage a'
    "t the reporting cut and replays fixed plus PERIOD_VC targets without proportio"
    "nal allocation; schedule overrides retain anchor-period realized consideration"
    " and recognize subsequent usage immediately; royalty and netted projections re"
    'main unavailable", "royalty manual projections freeze original statements and '
    "effective estimate pins at the reporting cut; minimum guarantees and recognize"
    "d royalty sources must remain stable over the frozen horizon; schedule overrid"
    'es retain anchor royalties and subsequent signed royalty changes separately", '
    '"Step-1 netted forecasts freeze original deposit recognitions and cite their a'
    "ttributed shares; a separate dated reporting remainder excludes already-recogn"
    "ized deposit revenue while preserving contract measurement balances; projected"
    ' future periods must reconcile to that net remainder", "original cancellation '
    "dates preserve pre-termination historical RPO and variance cuts; a single fixe"
    "d-only first-entry or same-version cancellation separates original modificatio"
    "ns and estimate changes from recognized revenue and cancelled remainder; trace"
    's without cancellation dates retain legacy behavior", "rpo_operational_hold_da'
    "tes_v1 dates retained RPO versions by business events; HOLD_APPLIED and HOLD_R"
    "ELEASED do not move a business change into the operational review month; hold-"
    "only computations keep the prior business date and original dated projection e"
    "vidence; older bindings retain their original version dates; database trace re"
    'ads preserve projection cut, period_key and refusal reason", "rpo_initial_elig'
    "ibility_timeline_v1 reads original Step 1 status nodes and their dated source "
    "events for eligibility-only initial computations; retained source identity and"
    " amounts are preserved across entry, exit and re-entry slices; pre-exit determ"
    "inistic schedules retain original-cut projections; monetary event batches and "
    "unavailable original evidence retain their previous behavior; older bindings r"
    'etain their original version timeline", "rpo_initial_monetary_timeline_v1 assi'
    "gns initial eligibility-batch amendments, and estimates to their original date"
    "s; event-specific shares and retained boundaries remove later same-period fixe"
    "d changes from lifecycle cuts; changes while excluded enter through the remain"
    "ing re-entry balance; same-day monetary events after a status transition requi"
    "re additional ordered evidence and retain the previous timeline; old bindings "
    'retain their original classification", "rpo_initial_usage_timeline_v1 assigns '
    "initial usage events to eligibility segments using original event-date realize"
    "d allocations; fees realized before exit are VC movements and fees realized wh"
    "ile excluded enter with the remaining re-entry balance; original date evidence"
    " is required and missing values are not replaced by month-end amounts; same-da"
    'y ordered limitations remain; older bindings keep their prior timeline", "rpo_'
    "initial_ordered_timeline_v1 attributes initial eligibility and monetary events"
    " in original date, record sequence and event-key order; original before/after "
    "allocation, realization and revenue evidence separates same-day exits and re-e"
    "ntries; changes while excluded enter with the remaining re-entry balance; miss"
    "ing required positions are not replaced with day-end amounts; historical bindi"
    'ngs preserve their original timeline", "rpo_initial_performance_timeline_v1 in'
    "cludes original delivery, return, billing and credit events in ordered initial"
    " eligibility timelines; net fixed allocation changes from performance and retu"
    "rn-window expiry are VC movements while included; excluded changes enter with "
    "the remaining re-entry balance; exact before-event amounts separate time-only "
    "releases from subsequent monetary causes; required original positions cannot b"
    "e replaced by date-only timelines; older bindings preserve their original inte"
    'rpretation", "historical_source_commit_v1 retains original event and contract-'
    "version transaction commits; new event/version extracts and BBR event sources "
    "use commit cutoffs; historical version populations exclude later commits befor"
    'e latest selection; bound inputs keep their original interpretation"], "parame'
    'ters": ["entity_codes", "book", "period_key", "period_lock_id", "time_bands", '
    '"row_dimension", "currency_view", "known_at", "known_at_basis"]}}, "rpo_rollfo'
    'rward": {"ipe_logic": {"version": 1, "source_tables": ["tenant", "fx_rate", "f'
    'x_rate_set", "fx_rate_set_version", "calc_trace", "obligation_version", "contr'
    'act_version", "contract_computation", "computation_evidence", "contract_event"'
    ', "contract", "period", "lock_snapshot", "combination_group_member", "historic'
    'al_source_commit"], "joins": ["obligation_version.contract_version_id = contra'
    'ct_version.id", "obligation_version.contract_id = contract.id", "contract_even'
    't.contract_id = contract.id", "combination_group_member.contract_id = contract'
    '.id", "calc_trace.contract_version_id = contract_version.id; estimate-event sh'
    'ares reconcile to original tp_delta nodes"], "filters": ["POL-199 excludes ori'
    "ginal realized royalty awaiting recognition, retaining fixed minimum guarantee"
    "s; POL-200 then applies to remaining eligible targeted VC; separate exemption "
    "rows and translated amounts reconcile to the combined cap; new retained RPO ru"
    'ns preserve this interpretation and old bindings keep their prior cap", "entit'
    'y code in entity_codes and within the caller\'s entity scope", "book_code = boo'
    'k", "opening: RPO at the end of the period before from_period_key; closing: RP'
    'O at the end of to_period_key", "per contract, the contract_version at the dat'
    "e along the contract's chain of combination groups: the versions recorded whil"
    'e the contract was a member of their group (combination_group_member)", "movem'
    'ents classified by the contract_event that caused each contract version", "ful'
    "l RPO exemption eligibility is evaluated per retained version; opening and clo"
    'sing exclusions are separate, with eligibility changes in EXEMPTIONS", "termin'
    "al cancellations remove only unrecognized allocation; retained cancelled-versi"
    'on revenue separates period recognition and late restatement", "cancellation a'
    "nd re-entry histories use separate disclosure segments; re-entry admits remain"
    'ing RPO and revenue excludes changes while outside disclosure", "mixed modific'
    "ation and estimate changes use original event-specific estimate shares reconci"
    'led to each price delta; unsupported or incomplete evidence stays unexplained"'
    ', "with period_lock_id, the values frozen at that lock (lock_snapshot kind RPO'
    '_ROLLFORWARD)", "measurement-only estimate pins prove no allocation movement; '
    "inception estimates and legacy pins without an explicit effect are not assumed"
    ' to have zero impact", "first-entry batches separate later original estimate s'
    "hares and dated fixed-boundary modification deltas from new contracts; modific"
    "ation decomposition requires complete event evidence and cancellations retain "
    'existing limits", "dated fixed-allocation evidence reconciles to version remai'
    "nders and excludes future changes from earlier RPO; same-version estimate and "
    "modification movements require original shares and boundary deltas matching th"
    'e dated allocation difference", "historical time-based schedules freeze the or'
    "iginal allocation segment at the reporting cut; dated projections reconcile to"
    ' the remainder and retain cut-specific drill-through", "original period projec'
    "tions survive removed current schedule lines; source evidence is the contract "
    'version trace for the exact reporting cut and future period", "scheduled and a'
    "waiting remainders use original period-level recognition-hold and pattern evid"
    "ence reconciled to the version state; future holds do not alter earlier time-b"
    'ased projections", "fixed-only manual releases, deferrals and schedule overrid'
    "es replay only events effective at the reporting cut; unsupported component mi"
    'xtures or unreproducible snapshots retain explicit projection errors", "exempt'
    "ion details retain obligation-level opening and closing exclusions, policy cod"
    "es and transaction-currency movement; translated views label this original bas"
    'is and legacy bindings retain their existing output shape", "manual projection'
    " freezes realized usage at the reporting cut and replays fixed plus PERIOD_VC "
    "targets without proportional allocation; schedule overrides retain anchor-peri"
    "od realized consideration and recognize subsequent usage immediately; royalty "
    'and netted projections remain unavailable", "royalty manual projections freeze'
    " original statements and effective estimate pins at the reporting cut; minimum"
    " guarantees and recognized royalty sources must remain stable over the frozen "
    "horizon; schedule overrides retain anchor royalties and subsequent signed roya"
    'lty changes separately", "Step-1 netted forecasts freeze original deposit reco'
    "gnitions and cite their attributed shares; a separate dated reporting remainde"
    "r excludes already-recognized deposit revenue while preserving contract measur"
    'ement balances; projected future periods must reconcile to that net remainder"'
    ', "new obligations added to an already disclosed contract follow modification '
    "and estimate causes instead of new contracts; first admission and re-entry kee"
    "p admission rules; bindings without rpo_added_obligations_v1 retain their orig"
    'inal classification", "translated RPO exemption details retain each contract-p'
    "eriod original movement and its monthly-average translated amount; details sum"
    " by report currency to EXEMPTIONS even when original range endpoints cancel; o"
    'lder bindings keep their existing controls", "first-batch added obligations ma'
    "y omit pre-creation boundaries only with original absent-before creation evide"
    "nce and independently retained earlier event order; zero allocation alone neve"
    'r proves absence and missing post-creation evidence remains unsupported", "mix'
    "ed terminal cancellations separate original modification and estimate deltas o"
    "nly when they reconcile from opening fixed allocation to the retained pre-term"
    "ination amount; missing or ambiguous event order remains unexplained and legac"
    'y bindings keep original classification", "mixed cancellation v2 admits same-d'
    "ay estimate changes only when immutable contract-event record sequence proves "
    "they precede the original termination boundary; later or missing order remains"
    ' unexplained; retained v1 keeps its date-only classification", "original cance'
    "llation dates preserve pre-termination historical RPO and variance cuts; a sin"
    "gle fixed-only first-entry or same-version cancellation separates original mod"
    "ifications and estimate changes from recognized revenue and cancelled remainde"
    'r; traces without cancellation dates retain legacy behavior", "rpo_cancelled_c'
    "hains_v1 settles original first-batch and opening-version cancellations before"
    " later retained versions; subsequent cancelled versions carry current retained"
    " revenue and re-entry admits only its remaining allocation; legacy bindings re"
    'tain prior classification", "rpo_cancelled_usage_v1 separates terminal realize'
    "d-fee changes from fixed cancellation attribution when opening and terminating"
    " versions both retain dated realization evidence; a single later termination u"
    "ses its realized amount, while fixed modifications and estimates still require"
    " the original pre-termination bridge; legacy bindings keep prior classificatio"
    'n", "rpo_cancelled_usage_v2 also separates dated realized fees in a single fir'
    "st-entry cancellation computation or an opening-to-closing cancellation within"
    " one retained version; realized changes are VC movements and cancellation remo"
    "ves fixed plus realized remainder net of recognized revenue; retained v1 keeps"
    ' its later-version-only behavior", "rpo_cancelled_usage_v3 carries realized-fe'
    "e attribution through subsequent versions only when every retained obligation "
    "stays cancelled and has dated realization evidence; final realized fees and re"
    "cognized revenue use the final retained source, while original fixed changes r"
    "etain their termination bridge; earlier v1 and v2 bindings preserve their clas"
    'sification", "rpo_cancelled_usage_v4 reads realized fees for each retained can'
    "cellation segment through the next re-entry cut; re-entry admits its fixed plu"
    "s realized allocation net of prior revenue and removes pre-entry realized fees"
    " from in-scope VC changes; retained v1-v3 bindings preserve prior classificati"
    'on", "rpo_cancelled_usage_v5 settles original first-batch and opening-version '
    "realized-fee cancellation at the next retained re-entry cut, including interve"
    "ning cancelled corrections, before admitting the new remaining allocation; ret"
    'ained v1-v4 preserve their classification", "new converted runs retain unexpla'
    "ined_details by source contract, entity, period and currency with original and"
    " already-translated differences; nonzero source differences remain reviewable "
    "even when they offset or round to zero; earlier bindings keep their existing c"
    'ontrol totals", "rpo_same_day_entry_cancel_v1 preserves new-contract, recogniz'
    "ed-revenue and cancellation movements for a single first fixed-only computatio"
    "n with same-day activation and original termination evidence; closing RPO rema"
    "ins zero and full exemptions still apply; other event mixtures and legacy bind"
    'ings retain prior behavior", "rpo_separate_cancellations_v1 permits multiple c'
    "ontract termination causes only when original per-obligation metadata identifi"
    "es one actual cancellation and every other termination has an explicitly retai"
    "ned zero fixed-allocation change for that obligation; incomplete or nonzero cr"
    'oss-effects remain unexplained; older bindings keep prior classification", "rp'
    "o_cancellation_cross_changes_v1 attributes original fixed-allocation changes f"
    "rom earlier partial terminations to cancellations, including first-entry and m"
    "onthly cuts; each termination must have explicit original state and nonzero cr"
    "oss-effects must precede the unique actual cancellation; the opening plus modi"
    "fications, estimates and cross-effects must reproduce its original before amou"
    'nt for mixed later-version attribution; older bindings retain prior behavior",'
    ' "rpo_continuing_cancellations_v1 separates original partial-termination alloc'
    "ation changes for obligations still disclosed at the period end, in first-entr"
    "y and same-version monthly cuts; every termination must retain explicit origin"
    "al state and the continuing obligation must not be cancelled within the cut; m"
    "onthly fixed movements must reconcile to dated allocations; older bindings ret"
    'ain prior classification", "rpo_mixed_continuing_changes_v1 separates original'
    " modification, estimate and partial-termination effects in a later retained ve"
    "rsion while the obligation remains disclosed; original event coverage and date"
    "s are required and their fixed amounts must sum to the actual version change; "
    "missing evidence or mismatched amounts remain unexplained; older bindings reta"
    'in prior attribution", "rpo_transaction_monthly_gaps_v1 checks each original c'
    "ontract/entity/period in transaction currency before range-level netting; any "
    "nonzero source difference fails the rollforward tie-out even when months offse"
    "t, and unexplained_details retains the original amount unchanged in report cur"
    "rency for viewer and exports; period cuts and the rule are retained for reruns"
    '; older transaction bindings keep their previous range-level checks", "rpo_tra'
    "nsaction_monthly_exemptions_v1 retains nonzero original contract/entity/period"
    " exemption movements in transaction-currency reports, including intermediate e"
    "ntry and exit hidden by range endpoint disclosures; exemption_translation hold"
    "s unchanged original and report amounts for the shared detail schema, labelled"
    " as monthly movements without claiming FX translation or equality to the range"
    " endpoint-based Exemptions line; older transaction bindings retain their prior"
    ' detail population", "rpo_same_day_entry_chains_v1 preserves original same-day'
    " activation and cancellation gross movements when subsequent retained versions"
    " exist; subsequent disclosure re-entry admits only its remaining balance, with"
    "out duplicating pre- entry revenue; original termination boundaries and dated "
    "realization remain required; older bindings retain their single-version eligib"
    'ility", "rpo_pretermination_versions_v1 carries original pre-termination fixed'
    " balances across intervening retained versions instead of settling a future ca"
    "ncellation early; the superseding computation determines the pending terminati"
    "on and version deltas retain their own cause attribution; original boundary an"
    "d dated realization guards remain required; older bindings retain prior treatm"
    'ent", "rpo_same_day_entry_modifications_v1 separates original contract amendme'
    "nts between same-day activation and termination from new-contract amounts; ori"
    "ginal admission and amendment record order, complete boundaries and continuity"
    " through the termination before-state are required; later re-entry does not re"
    'peat the amendment; older bindings retain their previous eligibility", "rpo_sa'
    "me_day_entry_estimates_v1 retains original inception estimates in new- contrac"
    "t amounts when activation and termination share a day; every estimate requires"
    " an original INCEPTION pin and an admission-date event; amendments remain sepa"
    "rately classified from original boundaries; missing evidence and older binding"
    's retain their previous eligibility", "rpo_same_day_entry_usage_v1 separates d'
    "ated realized fees from new-contract amounts for same-day activation and termi"
    "nation; original termination before-state and traced realized amounts are requ"
    "ired; original amendments remain separate and retained fee corrections use the"
    " cancelled chain; missing evidence and older bindings retain their previous el"
    'igibility", "rpo_eligibility_changes_v1 separately reports retained collectibi'
    "lity exits and criteria-met re-entry as contract eligibility changes; unchange"
    "d fixed allocation and dated realized evidence are required at exit; re-entry "
    "includes only the remaining balance and excludes prior-segment revenue; old bi"
    'ndings retain their original classification and report columns", "rpo_operatio'
    "nal_hold_dates_v1 dates retained RPO versions by business events; HOLD_APPLIED"
    " and HOLD_RELEASED do not move a business change into the operational review m"
    "onth; hold-only computations keep the prior business date and original dated p"
    "rojection evidence; older bindings retain their original version dates; databa"
    'se trace reads preserve projection cut, period_key and refusal reason", "rpo_m'
    "ixed_eligibility_v1 separates original amendment and estimate allocations from"
    " retained collectibility exits; complete event evidence dated no later than th"
    "e exit must reconcile the fixed change; dated realized fees remain VC movement"
    "s and the resulting remaining balance leaves through eligibility changes; olde"
    'r bindings retain their previous classification", "rpo_initial_eligibility_tim'
    "eline_v1 reads original Step 1 status nodes and their dated source events for "
    "eligibility-only initial computations; retained source identity and amounts ar"
    "e preserved across entry, exit and re-entry slices; pre-exit deterministic sch"
    "edules retain original-cut projections; monetary event batches and unavailable"
    " original evidence retain their previous behavior; older bindings retain their"
    ' original version timeline", "rpo_initial_monetary_timeline_v1 assigns initial'
    " eligibility-batch amendments, and estimates to their original dates; event-sp"
    "ecific shares and retained boundaries remove later same-period fixed changes f"
    "rom lifecycle cuts; changes while excluded enter through the remaining re-entr"
    "y balance; same-day monetary events after a status transition require addition"
    "al ordered evidence and retain the previous timeline; old bindings retain thei"
    'r original classification", "rpo_initial_usage_timeline_v1 assigns initial usa'
    "ge events to eligibility segments using original event-date realized allocatio"
    "ns; fees realized before exit are VC movements and fees realized while exclude"
    "d enter with the remaining re-entry balance; original date evidence is require"
    "d and missing values are not replaced by month-end amounts; same-day ordered l"
    'imitations remain; older bindings keep their prior timeline", "rpo_initial_ord'
    "ered_timeline_v1 attributes initial eligibility and monetary events in origina"
    "l date, record sequence and event-key order; original before/after allocation,"
    " realization and revenue evidence separates same-day exits and re-entries; cha"
    "nges while excluded enter with the remaining re-entry balance; missing require"
    "d positions are not replaced with day-end amounts; historical bindings preserv"
    'e their original timeline", "rpo_initial_performance_timeline_v1 includes orig'
    "inal delivery, return, billing and credit events in ordered initial eligibilit"
    "y timelines; net fixed allocation changes from performance and return-window e"
    "xpiry are VC movements while included; excluded changes enter with the remaini"
    "ng re-entry balance; exact before-event amounts separate time-only releases fr"
    "om subsequent monetary causes; required original positions cannot be replaced "
    'by date-only timelines; older bindings preserve their original interpretation"'
    ', "historical_source_commit_v1 retains original event and contract-version tra'
    "nsaction commits; new event/version extracts and BBR event sources use commit "
    "cutoffs; historical version populations exclude later commits before latest se"
    'lection; bound inputs keep their original interpretation"], "parameters": ["en'
    'tity_codes", "book", "period_lock_id", "from_period_key", "to_period_key", "cu'
    'rrency_view", "known_at", "known_at_basis"]}}, "variance_between_closes": {"ip'
    'e_logic": {"version": 1, "source_tables": ["period_lock", "lock_snapshot", "di'
    'sclosure_snapshot", "contract"], "joins": ["lock_snapshot.period_lock_id = per'
    'iod_lock.id", "disclosure_snapshot.period_lock_id = period_lock.id"], "filters'
    '": ["POL-199 excludes original realized royalty awaiting recognition, retainin'
    "g fixed minimum guarantees; POL-200 then applies to remaining eligible targete"
    "d VC; separate exemption rows and translated amounts reconcile to the combined"
    " cap; new retained RPO runs preserve this interpretation and old bindings keep"
    ' their prior cap", "two locks of one entity, book and period; the later record'
    'ed after the earlier", "locks of an entity in entity_codes", "changes attribut'
    'ed to drivers"], "parameters": ["entity_codes", "from_period_lock_id", "to_per'
    'iod_lock_id", "currency_view", "known_at", "known_at_basis"]}}}'
)


def _metadata(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for code, values in json.loads(encoded).items():
        payload = json.dumps(values["ipe_logic"]).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic='"  # noqa: S608 — frozen metadata
            + payload
            + "'::jsonb WHERE code='"
            + code
            + "' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)

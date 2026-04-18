import SwiftUI
import Charts

struct StatisticsPageView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    @State private var selectedExam = "Kaikki kokeet"
    @State private var selectedExercise = "Kaikki tehtävät"
    @State private var selectedStudent = "Kaikki opiskelijat"
    @State private var selectedPoints = "Kaikki pisteet"
    @State private var selectedStatus = "Kaikki tilat"
    @State private var selectedStudentSummaryID: StudentExamPerformanceSummary.ID?

    var body: some View {
        IntegratedPageSurface {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    if let statisticsErrorMessage = store.statisticsErrorMessage {
                        StatisticsCard(title: "Tilastojen lataus", subtitle: "Tilastosivun tiedot eivät juuri nyt päivittyneet.") {
                            Text(statisticsErrorMessage)
                                .font(.system(size: 13, weight: .medium, design: .rounded))
                                .foregroundStyle(Theme.ink)
                                .textSelection(.enabled)
                        }
                    }
                    filters
                    metrics

                    if !hasVisibleStatisticsData {
                        EmptyStateView(
                            title: "Ei tilastoja",
                            message: "Kun arvioit tehtäviä tai avaat Sanoman yleisnäkymän, tiedot kertyvät tänne kokeen, tehtävän ja opiskelijasuorituksen mukaan analysoitaviksi."
                        )
                        .frame(maxWidth: .infinity, minHeight: 320, alignment: .center)
                    } else {
                        chartsSection
                        exerciseSummarySection
                        interruptedSummarySection
                        studentPerformanceSection
                        selectedStudentSection
                    }
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
                .padding(.bottom, 8)
            }
            .scrollIndicators(.visible)
        }
        .task {
            await store.refreshStatistics()
            syncSelectedStudentSummaryIfNeeded()
        }
        .onChange(of: store.statisticsRuns) { _, _ in
            normalizeFilterSelections()
            syncSelectedStudentSummaryIfNeeded()
        }
        .onChange(of: selectedExam) { _, _ in
            selectedExercise = "Kaikki tehtävät"
            selectedStudent = "Kaikki opiskelijat"
            selectedPoints = "Kaikki pisteet"
            syncSelectedStudentSummaryIfNeeded()
        }
        .onChange(of: selectedExercise) { _, _ in
            normalizeFilterSelections()
            syncSelectedStudentSummaryIfNeeded()
        }
        .onChange(of: selectedStudent) { _, _ in
            normalizeFilterSelections()
            syncSelectedStudentSummaryIfNeeded()
        }
        .onChange(of: selectedPoints) { _, _ in
            syncSelectedStudentSummaryIfNeeded()
        }
        .onChange(of: selectedStatus) { _, _ in
            normalizeFilterSelections()
            syncSelectedStudentSummaryIfNeeded()
        }
        .onChange(of: store.hideStudentNamesInGui) { _, _ in
            normalizeFilterSelections()
            syncSelectedStudentSummaryIfNeeded()
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Tilastot")
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.ink)
                Text("Kokeet, tehtävät ja opiskelijoiden suoriutuminen yhdessä näkymässä")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.inkMuted)
            }

            Spacer(minLength: 0)

            Button {
                Task { await store.refreshStatistics() }
            } label: {
                Label("Päivitä", systemImage: "arrow.clockwise")
            }
            .buttonStyle(LiquidGlassButtonStyle(tint: Theme.neutral))
        }
    }

    private var filters: some View {
        VStack(alignment: .leading, spacing: 12) {
            AdaptiveAxisStack(horizontal: !compact, spacing: 12) {
                StatisticsFilterPicker(
                    title: "Koe",
                    selection: $selectedExam,
                    options: ["Kaikki kokeet"] + examOptions
                )
                StatisticsFilterPicker(
                    title: "Tehtävä",
                    selection: $selectedExercise,
                    options: ["Kaikki tehtävät"] + exerciseOptions
                )
                StatisticsFilterPicker(
                    title: "Opiskelija",
                    selection: $selectedStudent,
                    options: ["Kaikki opiskelijat"] + studentOptions
                )
            }

            AdaptiveAxisStack(horizontal: !compact, spacing: 12) {
                StatisticsFilterPicker(
                    title: "Pisteet",
                    selection: $selectedPoints,
                    options: ["Kaikki pisteet"] + pointsOptions
                )
                StatisticsFilterPicker(
                    title: "Tila",
                    selection: $selectedStatus,
                    options: ["Kaikki tilat"] + statusOptions,
                    display: { option in
                        option == "Kaikki tilat" ? option : localizedStatus(option)
                    }
                )
            }
        }
    }

    private var metrics: some View {
        AdaptiveAxisStack(horizontal: !compact, spacing: 12) {
            StatisticsMetricTile(title: "Kokeet", value: "\(uniqueExamCount)", subtitle: "Suodatuksessa mukana")
            StatisticsMetricTile(title: "Tehtävät", value: "\(exerciseSummaryCount)", subtitle: "Tehtäväkohtaiset koosteet")
            StatisticsMetricTile(title: "Oppilaat", value: "\(uniqueStudentCount)", subtitle: "Uniikit opiskelijat")
            StatisticsMetricTile(title: "Yleisnäkymä", value: "\(overviewObservedScoreCount)", subtitle: "Suoraan matriisista luetut pisteet")
            StatisticsMetricTile(title: "Keskeytyneet", value: "\(interruptedRunCount)", subtitle: "Osittain tallentuneet arvioinnit")
            StatisticsGaugeTile(title: "Keskiarvo", value: averageScoreRatio, subtitle: "Pisteosuus kaikista merkinnöistä")
        }
    }

    private var chartsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            AdaptiveAxisStack(horizontal: !compact, spacing: 14) {
                StatisticsCard(title: "Tehtävien keskipisteet", subtitle: "Valitun kokeen tehtävät korkeimmasta keskimääräisestä pisteosuudesta matalimpaan. Mukana myös yleisnäkymän sinisistä ruuduista luetut pisteet.") {
                    if exerciseRankingBars.isEmpty {
                        EmptyStateView(title: "Ei tehtävävertailua", message: "Valitse koe tai avaa yleisnäkymä, jotta tehtävien keskimääräiset pisteet voidaan järjestää.")
                    } else {
                        Chart(exerciseRankingBars) { bar in
                            BarMark(
                                x: .value("Pisteosuus", bar.averageRatio * 100),
                                y: .value("Tehtävä", bar.label)
                            )
                            .foregroundStyle(bar.color.gradient)
                            .cornerRadius(8)
                            .annotation(position: .trailing, alignment: .center) {
                                Text(bar.averagePointsText)
                                    .font(.system(size: 10, weight: .bold, design: .rounded))
                                    .foregroundStyle(Theme.ink)
                            }
                        }
                        .chartLegend(.hidden)
                        .chartXScale(domain: 0 ... 100)
                        .chartXAxis {
                            AxisMarks(values: .automatic(desiredCount: 5))
                        }
                        .chartYAxis {
                            AxisMarks(position: .leading)
                        }
                        .frame(minHeight: max(260.0, CGFloat(exerciseRankingBars.count) * 28))
                    }
                }

                StatisticsCard(title: "Tehtäväjakauma", subtitle: "Donitsikaavio valittujen tehtävien merkintämääristä.") {
                    if exerciseSlices.isEmpty {
                        EmptyStateView(title: "Ei tehtäviä", message: "Tehtäväjakauma näkyy, kun suodatuksessa on pisteytettyjä merkintöjä.")
                    } else {
                        Chart(exerciseSlices) { slice in
                            SectorMark(
                                angle: .value("Merkinnät", slice.value),
                                innerRadius: .ratio(0.56),
                                angularInset: 3
                            )
                            .foregroundStyle(slice.color)
                            .cornerRadius(6)
                        }
                        .chartLegend(position: .bottom, spacing: 12)
                        .frame(minHeight: 260)
                    }
                }
            }

            AdaptiveAxisStack(horizontal: !compact, spacing: 14) {
                StatisticsCard(title: "Arviointitilat", subtitle: "Jakautuminen arvioinnin lopputilan mukaan ilman pylväitä.") {
                    if statusSlices.isEmpty {
                        EmptyStateView(title: "Ei tilatietoja", message: "Tilat näkyvät, kun arviointimerkintöjä on tallentunut.")
                    } else {
                        Chart(statusSlices) { slice in
                            SectorMark(
                                angle: .value("Merkinnät", slice.value),
                                innerRadius: .ratio(0.52),
                                angularInset: 3
                            )
                            .foregroundStyle(slice.color)
                            .cornerRadius(6)
                        }
                        .chartLegend(position: .bottom, spacing: 12)
                        .frame(minHeight: 240)
                    }
                }

                StatisticsCard(title: "Pistepilvi", subtitle: "Yksittäiset oppilasmerkinnät pisteosuuden ja maksimipisteiden mukaan.") {
                    if scatterPoints.isEmpty {
                        EmptyStateView(title: "Ei pistepilveä", message: "Pistepilvi muodostuu, kun arvioinneilla on numeeriset pisteet.")
                    } else {
                        Chart(scatterPoints) { point in
                            PointMark(
                                x: .value("Maksimipisteet", point.scorePossible),
                                y: .value("Pisteosuus", point.ratio * 100)
                            )
                            .foregroundStyle(point.color)
                            .symbolSize(72)
                        }
                        .chartYAxis {
                            AxisMarks(position: .leading)
                        }
                        .chartXScale(domain: 0 ... maxScatterScore)
                        .chartYScale(domain: 0 ... 100)
                        .frame(minHeight: 240)
                    }
                }
            }
        }
    }

    private var exerciseSummarySection: some View {
        StatisticsCard(title: "Tehtäväkooste", subtitle: "Koe- ja tehtävätason yhteenveto kaikista näkyvistä arviointimerkinnöistä.") {
            Table(exerciseSummaries) {
                TableColumn("Koe") { summary in
                    Text(summary.examTitle)
                        .lineLimit(1)
                }
                TableColumn("Tehtävä") { summary in
                    Text(summary.exerciseDisplay)
                        .lineLimit(1)
                }
                TableColumn("Merkinnät") { summary in
                    Text("\(summary.entryCount)")
                }
                TableColumn("Oppilaat") { summary in
                    Text("\(summary.uniqueStudentCount)")
                }
                TableColumn("Keskiarvo") { summary in
                    Text(summary.averageRatio.map(StatisticsFormatting.percent) ?? "-")
                }
                TableColumn("Keskeytetyt") { summary in
                    Text("\(summary.interruptedRunCount)")
                }
            }
            .frame(minHeight: 220)
        }
    }

    private var interruptedSummarySection: some View {
        StatisticsCard(title: "Keskeytyneet arvioinnit", subtitle: "Osittaiset arvioinnit kokeittain ja tehtävittäin.") {
            if interruptedSummaries.isEmpty {
                EmptyStateView(title: "Ei keskeytyksiä", message: "Suodatuksessa ei ole yhtään keskeytynyttä arviointia.")
            } else {
                Table(interruptedSummaries) {
                    TableColumn("Koe") { summary in
                        Text(summary.assignmentTitle)
                            .lineLimit(1)
                    }
                    TableColumn("Tehtävä") { summary in
                        Text(summary.exerciseDisplay)
                            .lineLimit(1)
                    }
                    TableColumn("Ryhmä") { summary in
                        Text(summary.groupName ?? "-")
                            .lineLimit(1)
                    }
                    TableColumn("Tila") { summary in
                        Text(localizedStatus(summary.status))
                    }
                    TableColumn("Yhteenveto") { summary in
                        Text(summary.summary)
                            .lineLimit(2)
                    }
                }
                .frame(minHeight: 180)
            }
        }
    }

    private var studentPerformanceSection: some View {
        StatisticsCard(title: "Opiskelijakohtainen suoriutuminen", subtitle: "Yhteenveto opiskelijoiden suoriutumisesta koetasolla nykyisten suodattimien mukaan.") {
            Table(studentPerformanceSummaries, selection: $selectedStudentSummaryID) {
                TableColumn("Opiskelija") { summary in
                    Text(store.visibleStudentName(summary.studentName))
                        .lineLimit(1)
                }
                TableColumn("Koe") { summary in
                    Text(summary.assignmentTitle)
                        .lineLimit(1)
                }
                TableColumn("Ryhmä") { summary in
                    Text(summary.groupName ?? "-")
                        .lineLimit(1)
                }
                TableColumn("Tehtäviä") { summary in
                    Text("\(summary.exerciseCount)")
                }
                TableColumn("Merkintöjä") { summary in
                    Text("\(summary.entryCount)")
                }
                TableColumn("Keskiarvo") { summary in
                    Text(summary.averageRatio.map(StatisticsFormatting.percent) ?? "-")
                }
                TableColumn("Pisteet") { summary in
                    Text(summary.averagePointsText)
                }
                TableColumn("Paras tehtävä") { summary in
                    Text(summary.bestExerciseDisplay ?? "-")
                        .lineLimit(1)
                }
            }
            .frame(minHeight: 260)
        }
    }

    private var selectedStudentSection: some View {
        StatisticsCard(title: "Valittu opiskelija", subtitle: "Koekohtainen yhteenveto opiskelijan suoriutumisesta ja tehtäväkohtaisista tuloksista.") {
            if let summary = selectedStudentSummary {
                VStack(alignment: .leading, spacing: 14) {
                    AdaptiveAxisStack(horizontal: !compact, spacing: 10) {
                        StatisticsMetaPill(label: "Opiskelija", value: store.visibleStudentName(summary.studentName))
                        StatisticsMetaPill(label: "Ryhmä", value: summary.groupName ?? "-")
                        StatisticsMetaPill(label: "Koe", value: summary.assignmentTitle)
                        StatisticsMetaPill(label: "Tehtäviä", value: "\(summary.exerciseCount)")
                        StatisticsMetaPill(label: "Merkintöjä", value: "\(summary.entryCount)")
                        StatisticsMetaPill(label: "Keskiarvo", value: summary.averageRatio.map(StatisticsFormatting.percent) ?? "-")
                        StatisticsMetaPill(label: "Pisteet", value: summary.averagePointsText)
                    }

                    AdaptiveAxisStack(horizontal: !compact, spacing: 10) {
                        StatisticsMetaPill(label: "Paras tehtävä", value: summary.bestExerciseDisplay ?? "-")
                        StatisticsMetaPill(label: "Heikoin tehtävä", value: summary.weakestExerciseDisplay ?? "-")
                        StatisticsMetaPill(label: "Arvioidut", value: "\(summary.gradedEntryCount)")
                        StatisticsMetaPill(label: "Yleisnäkymä", value: "\(summary.overviewObservedCount)")
                    }

                    StatisticsDetailBlock(
                        title: "Tehtäväkohtainen yhteenveto",
                        text: summary.exerciseBreakdownText
                    )
                }
            } else {
                EmptyStateView(title: "Valitse opiskelija", message: "Valitse opiskelija taulukosta nähdäksesi koekohtaisen yhteenvedon.")
            }
        }
    }

    private var examOptions: [String] {
        Array(
            Set(
                allEntryRecords
                    .map(\.assignmentTitle)
                    .filter { !$0.isEmpty }
                + store.statisticsRuns
                    .map(\.assignmentTitle)
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }
            )
        )
        .sorted()
    }

    private var exerciseOptions: [String] {
        Array(
            Set(
                entryRecordsMatchingExamAndStatus.compactMap(\.exerciseDisplay)
                + runsMatchingExamAndStatus.compactMap { exerciseFilterValue(for: $0) }
            )
        )
        .sorted()
    }

    private var studentOptions: [String] {
        Array(
            Set(
                entryRecordsMatchingExamExerciseStatusBase
                    .map { store.visibleStudentName($0.studentName).trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }
            )
        )
        .sorted()
    }

    private var pointsOptions: [String] {
        Array(
            Set(
                entryRecordsMatchingExamExerciseStatusBase
                    .map { $0.pointsText.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }
            )
        )
        .sorted()
    }

    private var statusOptions: [String] {
        Array(
            Set(
                store.statisticsRuns.map(\.status)
                + allEntryRecords.map(\.status)
            )
        )
        .sorted()
    }

    private var allEntryRecords: [StatisticsEntryRecord] {
        var mergedByKey: [String: StatisticsEntryRecord] = [:]

        for run in store.statisticsRuns {
            for entry in run.entries {
                let record = StatisticsEntryRecord(run: run, entry: entry)
                let key = record.dedupeKey
                if let existing = mergedByKey[key] {
                    mergedByKey[key] = record.preferred(over: existing)
                } else {
                    mergedByKey[key] = record
                }
            }
        }

        if let overview = store.overview {
            for observedScore in overview.observedScores {
                let record = StatisticsEntryRecord(
                    overviewScore: observedScore,
                    assignmentTitle: overview.assignmentTitle,
                    groupName: overview.groupName
                )
                let key = record.dedupeKey
                if let existing = mergedByKey[key] {
                    mergedByKey[key] = record.preferred(over: existing)
                } else {
                    mergedByKey[key] = record
                }
            }
        }

        return mergedByKey.values.sorted { leftRecord, rightRecord in
            if leftRecord.assignmentTitle == rightRecord.assignmentTitle {
                if leftRecord.exerciseSortKey == rightRecord.exerciseSortKey {
                    return store.visibleStudentName(leftRecord.studentName) < store.visibleStudentName(rightRecord.studentName)
                }
                return leftRecord.exerciseSortKey < rightRecord.exerciseSortKey
            }
            return leftRecord.assignmentTitle < rightRecord.assignmentTitle
        }
    }

    private var runsMatchingExamAndStatus: [GuiStatisticsRun] {
        store.statisticsRuns.filter { run in
            let examMatches = selectedExam == "Kaikki kokeet" || run.assignmentTitle == selectedExam
            let statusMatches = selectedStatus == "Kaikki tilat" || run.status == selectedStatus
            return examMatches && statusMatches
        }
    }

    private var entryRecordsMatchingExamExerciseStatusBase: [StatisticsEntryRecord] {
        entryRecordsMatchingExamAndStatus.filter { record in
            let exerciseMatches = selectedExercise == "Kaikki tehtävät" || record.exerciseDisplay == selectedExercise
            return exerciseMatches
        }
    }

    private var entryRecordsMatchingExamAndStatus: [StatisticsEntryRecord] {
        allEntryRecords.filter { record in
            let examMatches = selectedExam == "Kaikki kokeet" || record.assignmentTitle == selectedExam
            let statusMatches = selectedStatus == "Kaikki tilat" || record.status == selectedStatus
            return examMatches && statusMatches
        }
    }

    private var filteredEntryRecords: [StatisticsEntryRecord] {
        entryRecordsMatchingExamExerciseStatusBase.filter { record in
            let studentMatches = selectedStudent == "Kaikki opiskelijat" || store.visibleStudentName(record.studentName) == selectedStudent
            let pointsMatches = selectedPoints == "Kaikki pisteet" || record.pointsText == selectedPoints
            return studentMatches && pointsMatches
        }
    }

    private var filteredRuns: [GuiStatisticsRun] {
        let matchingRunIDs = Set(filteredEntryRecords.compactMap(\.runID))
        let entryLevelFilterActive = selectedStudent != "Kaikki opiskelijat" || selectedPoints != "Kaikki pisteet"
        return runsMatchingExamAndStatus.filter { run in
            let exerciseMatches = selectedExercise == "Kaikki tehtävät" || exerciseFilterValue(for: run) == selectedExercise
            guard exerciseMatches else { return false }
            if !entryLevelFilterActive {
                return true
            }
            return matchingRunIDs.contains(run.id)
        }
    }

    private var filteredEntryCount: Int {
        filteredEntryRecords.count
    }

    private var uniqueExamCount: Int {
        Set(
            filteredEntryRecords.map(\.assignmentTitle).filter { !$0.isEmpty }
            + filteredRuns.map(\.assignmentTitle).filter { !$0.isEmpty }
        ).count
    }

    private var exerciseSummaryCount: Int {
        exerciseSummaries.count
    }

    private var uniqueStudentCount: Int {
        Set(
            filteredEntryRecords
                .map { store.visibleStudentName($0.studentName).trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
        ).count
    }

    private var overviewObservedScoreCount: Int {
        filteredEntryRecords.filter(\.isOverviewObserved).count
    }

    private var interruptedRunCount: Int {
        filteredRuns.filter { $0.interrupted == true }.count
    }

    private var averageScoreRatio: Double {
        let ratios = filteredEntryRecords.compactMap(\.scoreRatio)
        guard !ratios.isEmpty else { return 0 }
        return ratios.reduce(0, +) / Double(ratios.count)
    }

    private var hasVisibleStatisticsData: Bool {
        !filteredEntryRecords.isEmpty || !interruptedSummaries.isEmpty
    }

    private var studentPerformanceSummaries: [StudentExamPerformanceSummary] {
        let grouped = Dictionary(grouping: filteredEntryRecords) { record in
            StudentExamPerformanceKey(
                assignmentTitle: record.assignmentTitle,
                groupName: record.groupName,
                studentName: store.visibleStudentName(record.studentName)
            )
        }

        return grouped.keys.sorted { leftKey, rightKey in
            if leftKey.assignmentTitle == rightKey.assignmentTitle {
                return leftKey.studentName < rightKey.studentName
            }
            return leftKey.assignmentTitle < rightKey.assignmentTitle
        }.compactMap { key in
            let records = grouped[key] ?? []
            guard !records.isEmpty else { return nil }
            return StudentExamPerformanceSummary(
                assignmentTitle: key.assignmentTitle,
                groupName: key.groupName,
                studentName: key.studentName,
                records: records
            )
        }
    }

    private var selectedStudentSummary: StudentExamPerformanceSummary? {
        if let selectedStudentSummaryID {
            return studentPerformanceSummaries.first(where: { $0.id == selectedStudentSummaryID }) ?? studentPerformanceSummaries.first
        }
        return studentPerformanceSummaries.first
    }

    private var exerciseSlices: [StatisticsSlice] {
        let grouped = Dictionary(grouping: filteredEntryRecords) { record in
            record.exerciseDisplay ?? "Muu tehtävä"
        }
        let palette = [
            Color(hex: "#2F6B4F"),   // sage
            Color(hex: "#C9A96A"),   // ochre
            Color(hex: "#B8654A"),   // terracotta
            Color(hex: "#5E6773"),   // slate
            Color(hex: "#8A6C9E"),   // heather
            Color(hex: "#4F7A8C"),   // steel blue
        ]
        return grouped.keys.sorted().enumerated().map { index, key in
            StatisticsSlice(label: key, value: grouped[key]?.count ?? 0, color: palette[index % palette.count])
        }
    }

    private var statusSlices: [StatisticsSlice] {
        let grouped = Dictionary(grouping: filteredRuns, by: \.status)
        return grouped.keys.sorted().map { key in
            StatisticsSlice(label: localizedStatus(key), value: grouped[key]?.count ?? 0, color: colorForStatus(key))
        }
    }

    private var exerciseRankingBars: [ExerciseRankingBar] {
        let grouped = Dictionary(grouping: filteredEntryRecords) { record in
            record.exerciseDisplay ?? "Tuntematon tehtävä"
        }
        let palette = [
            Color(hex: "#2F6B4F"),   // sage
            Color(hex: "#4F7A8C"),   // steel blue
            Color(hex: "#C9A96A"),   // ochre
            Color(hex: "#B8654A"),   // terracotta
            Color(hex: "#8A6C9E"),   // heather
            Color(hex: "#5E6773"),   // slate
        ]
        return grouped.keys.sorted().enumerated().compactMap { index, key in
            let records = grouped[key] ?? []
            let scoredRecords = records.filter { $0.scoreRatio != nil }
            guard !scoredRecords.isEmpty else { return nil }
            let averageRatio = scoredRecords.compactMap(\.scoreRatio).reduce(0, +) / Double(scoredRecords.count)
            let awardedValues = scoredRecords.compactMap(\.scoreAwarded)
            let possibleValues = scoredRecords.compactMap(\.scorePossible)
            let averageAwarded = awardedValues.isEmpty ? nil : awardedValues.reduce(0, +) / Double(awardedValues.count)
            let averagePossible = possibleValues.isEmpty ? nil : possibleValues.reduce(0, +) / Double(possibleValues.count)
            return ExerciseRankingBar(
                label: key,
                averageRatio: averageRatio,
                averageAwarded: averageAwarded,
                averagePossible: averagePossible,
                sampleCount: scoredRecords.count,
                color: palette[index % palette.count]
            )
        }
        .sorted { leftBar, rightBar in
            if abs(leftBar.averageRatio - rightBar.averageRatio) > 0.0001 {
                return leftBar.averageRatio > rightBar.averageRatio
            }
            return leftBar.label < rightBar.label
        }
    }

    private var scatterPoints: [StatisticsScatterPoint] {
        filteredEntryRecords.compactMap { record in
            guard let ratio = record.scoreRatio,
                  let scorePossible = record.scorePossible else {
                return nil
            }
            return StatisticsScatterPoint(
                id: record.id,
                scorePossible: scorePossible,
                ratio: ratio,
                color: colorForCategory(record.categoryName)
            )
        }
    }

    private var exerciseSummaries: [ExerciseStatisticsSummary] {
        let filteredRunIDs = Set(filteredRuns.map(\.id))
        let groupedEntries = Dictionary(grouping: filteredEntryRecords) { record in
            ExerciseSummaryKey(
                examTitle: record.assignmentTitle,
                exerciseDisplay: record.exerciseDisplay ?? "Tuntematon tehtävä"
            )
        }
        let groupedRuns = Dictionary(grouping: filteredRuns) { run in
            ExerciseSummaryKey(
                examTitle: run.assignmentTitle,
                exerciseDisplay: exerciseFilterValue(for: run) ?? "Tuntematon tehtävä"
            )
        }

        let keys = Set(groupedEntries.keys).union(groupedRuns.keys)
        return keys.sorted { lhs, rhs in
            if lhs.examTitle == rhs.examTitle {
                return lhs.exerciseDisplay < rhs.exerciseDisplay
            }
            return lhs.examTitle < rhs.examTitle
        }.map { key in
            let records = groupedEntries[key] ?? []
            let runs = (groupedRuns[key] ?? []).filter { filteredRunIDs.contains($0.id) }
            let ratios = records.compactMap(\.scoreRatio)
            return ExerciseStatisticsSummary(
                examTitle: key.examTitle,
                exerciseDisplay: key.exerciseDisplay,
                entryCount: records.count,
                uniqueStudentCount: Set(
                    records
                        .map { store.visibleStudentName($0.studentName).trimmingCharacters(in: .whitespacesAndNewlines) }
                        .filter { !$0.isEmpty }
                ).count,
                averageRatio: ratios.isEmpty ? nil : ratios.reduce(0, +) / Double(ratios.count),
                interruptedRunCount: runs.filter { $0.interrupted == true }.count
            )
        }
    }

    private var interruptedSummaries: [InterruptedStatisticsSummary] {
        filteredRuns
            .filter { $0.interrupted == true }
            .map { run in
                InterruptedStatisticsSummary(
                    assignmentTitle: run.assignmentTitle,
                    groupName: run.groupName,
                    exerciseDisplay: exerciseFilterValue(for: run) ?? "Tuntematon tehtävä",
                    status: run.status,
                    summary: run.summary
                )
            }
    }

    private func exerciseFilterValue(for run: GuiStatisticsRun) -> String? {
        Self.exerciseDisplay(
            categoryName: run.categoryName,
            exerciseLabel: run.exerciseLabel,
            exerciseNumber: run.exerciseNumber
        )
    }

    private func exerciseFilterValue(for entry: GuiStatisticsEntry, in run: GuiStatisticsRun) -> String? {
        Self.exerciseDisplay(
            categoryName: entry.categoryName ?? run.categoryName,
            exerciseLabel: entry.exerciseLabel ?? run.exerciseLabel,
            exerciseNumber: entry.exerciseNumber ?? run.exerciseNumber
        )
    }

    private static func exerciseDisplay(
        categoryName: String?,
        exerciseLabel: String?,
        exerciseNumber: String?
    ) -> String? {
        let category = categoryName?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfBlank
        let label = exerciseLabel?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfBlank
        let number = exerciseNumber?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfBlank

        if let category, let number {
            return "\(category) · Tehtävä \(number)"
        }
        if let category, let label {
            return "\(category) · \(label)"
        }
        if let label {
            return label
        }
        if let number {
            return "Tehtävä \(number)"
        }
        return nil
    }

    private func normalizeFilterSelections() {
        if selectedExam != "Kaikki kokeet" && !examOptions.contains(selectedExam) {
            selectedExam = "Kaikki kokeet"
        }
        if selectedExercise != "Kaikki tehtävät" && !exerciseOptions.contains(selectedExercise) {
            selectedExercise = "Kaikki tehtävät"
        }
        if selectedStudent != "Kaikki opiskelijat" && !studentOptions.contains(selectedStudent) {
            selectedStudent = "Kaikki opiskelijat"
        }
        if selectedPoints != "Kaikki pisteet" && !pointsOptions.contains(selectedPoints) {
            selectedPoints = "Kaikki pisteet"
        }
        if selectedStatus != "Kaikki tilat" && !statusOptions.contains(selectedStatus) {
            selectedStatus = "Kaikki tilat"
        }
    }

    private func syncSelectedStudentSummaryIfNeeded() {
        if selectedStudentSummary == nil {
            selectedStudentSummaryID = studentPerformanceSummaries.first?.id
        }
    }

    private var maxScatterScore: Double {
        max(scatterPoints.map(\.scorePossible).max() ?? 1, 1)
    }

    private func localizedStatus(_ status: String) -> String {
        switch status {
        case "completed", "scored":
            return "Valmis"
        case "needs_review":
            return "Tarkistettava"
        case "failed":
            return "Epäonnistui"
        case "dry_run":
            return "Kuiva arviointi"
        case "observed":
            return "Havaittu"
        default:
            return status
        }
    }

    private func colorForStatus(_ status: String) -> Color {
        switch status {
        case "completed", "scored":
            return Color(hex: "#2F6B4F")   // sage
        case "needs_review":
            return Color(hex: "#C9A96A")   // ochre
        case "failed":
            return Color(hex: "#B8654A")   // terracotta
        case "dry_run":
            return Color(hex: "#5E6773")   // slate
        case "observed":
            return Color(hex: "#4F7A8C")   // steel blue
        default:
            return Color(hex: "#8A93A0")   // inkSoft
        }
    }

    private func colorForCategory(_ category: String?) -> Color {
        switch (category ?? "").lowercased() {
        case let value where value.contains("text"):
            return Color(hex: "#2F6B4F")   // sage
        case let value where value.contains("kuuntelut"):
            return Color(hex: "#4F7A8C")   // steel blue
        case let value where value.contains("gramm"):
            return Color(hex: "#C9A96A")   // ochre
        case let value where value.contains("skriv"):
            return Color(hex: "#B8654A")   // terracotta
        default:
            return Color(hex: "#8A6C9E")   // heather
        }
    }
}

struct LogsPageView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    @State private var searchText = ""

    var body: some View {
        IntegratedPageSurface {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    if let statisticsErrorMessage = store.statisticsErrorMessage {
                        StatisticsCard(title: "Lokien lataus", subtitle: "Lokitietojen hakeminen ei onnistunut juuri nyt.") {
                            Text(statisticsErrorMessage)
                                .font(.system(size: 13, weight: .medium, design: .rounded))
                                .foregroundStyle(Theme.inkMuted)
                                .textSelection(.enabled)
                        }
                    }
                    metrics

                    if filteredLogs.isEmpty {
                        EmptyStateView(
                            title: "Ei lokeja",
                            message: "Kun arvioit tehtäviä Ohjaus-sivulla, jokaisesta oppilasvastauksesta tallentuu tänne tarkka loki promptteineen ja mallivastauksineen."
                        )
                        .frame(maxWidth: .infinity, minHeight: 320)
                    } else {
                        LazyVStack(spacing: 14) {
                            ForEach(filteredLogs) { log in
                                LogEntryCard(log: log, compact: compact)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
                .padding(.bottom, 8)
            }
            .scrollIndicators(.visible)
        }
        .searchable(text: $searchText, prompt: "Hae opiskelijaa, tehtävää, koetta tai mallia")
        .task {
            await store.refreshStatistics()
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Lokit")
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.ink)
                Text("Tarkastele arvioituja oppilasvastauksia: tehtäväkonteksti, lähetetty prompti, käytetty malli ja mallin perustelut.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.inkMuted)
            }

            Spacer(minLength: 0)

            Button {
                Task { await store.refreshStatistics() }
            } label: {
                Label("Päivitä", systemImage: "arrow.clockwise")
            }
            .buttonStyle(LiquidGlassButtonStyle(tint: Theme.neutral))
        }
    }

    private var metrics: some View {
        AdaptiveAxisStack(horizontal: !compact, spacing: 12) {
            StatisticsMetricTile(title: "Lokit", value: "\(filteredLogs.count)", subtitle: "Yksittäiset arviointimerkinnät")
            StatisticsMetricTile(title: "Kokeet", value: "\(Set(filteredLogs.map(\.assignmentTitle)).count)", subtitle: "Lokeissa näkyvät kokeet")
            StatisticsMetricTile(title: "Tehtävät", value: "\(Set(filteredLogs.compactMap { $0.exerciseLabel ?? $0.exerciseNumber }).count)", subtitle: "Lokeissa näkyvät tehtävät")
            StatisticsMetricTile(title: "Mallit", value: "\(Set(filteredLogs.map(\.modelDisplay)).count)", subtitle: "Käytetyt mallit")
            StatisticsMetricTile(title: "Fallback", value: "\(filteredLogs.filter(\.usedHeuristicFallback).count)", subtitle: "Heuristiset varapolut")
        }
    }

    private var filteredLogs: [StatisticsLogRecord] {
        allLogs.filter { log in
            let trimmedQuery = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmedQuery.isEmpty else { return true }
            let haystack = [
                log.studentName,
                log.studentProgress,
                log.assignmentTitle,
                log.groupName,
                log.categoryName,
                log.exerciseLabel,
                log.exerciseNumber,
                log.promptTitle,
                log.modelDisplay,
                log.targetText,
                log.answerText,
                log.modelAnswerText,
                log.submittedPromptText,
                log.modelResponseText,
                log.reasoningText,
            ]
            .compactMap { $0 }
            .joined(separator: "\n")
            return haystack.localizedCaseInsensitiveContains(trimmedQuery)
        }
    }

    private var allLogs: [StatisticsLogRecord] {
        store.statisticsRuns.flatMap { run in
            if run.entries.isEmpty {
                return [StatisticsLogRecord(run: run, entry: nil)]
            }
            return run.entries.map { entry in
                StatisticsLogRecord(run: run, entry: entry)
            }
        }
    }
}

private struct StatisticsSlice: Identifiable {
    let label: String
    let value: Int
    let color: Color

    var id: String { label }
}

private struct StatisticsScatterPoint: Identifiable {
    let id: String
    let scorePossible: Double
    let ratio: Double
    let color: Color
}

private struct ExerciseRankingBar: Identifiable {
    let label: String
    let averageRatio: Double
    let averageAwarded: Double?
    let averagePossible: Double?
    let sampleCount: Int
    let color: Color

    var id: String { label }

    var averagePointsText: String {
        guard let averageAwarded, let averagePossible, averagePossible > 0 else {
            return "\(sampleCount) merk."
        }
        return "\(StatisticsFormatting.decimal(averageAwarded)) / \(StatisticsFormatting.decimal(averagePossible))"
    }
}

private struct StatisticsEntryRecord: Identifiable {
    enum Source {
        case graded
        case overview
    }

    let source: Source
    let assignmentTitle: String
    let groupName: String?
    let categoryName: String?
    let exerciseLabel: String?
    let exerciseNumber: String?
    let studentName: String
    let studentProgress: String?
    let pointsText: String
    let scoreAwarded: Double?
    let scorePossible: Double?
    let status: String
    let runID: String?
    let objectiveText: String
    let targetText: String
    let answerText: String
    let modelAnswerText: String
    let basisLines: [String]
    let exerciseURL: String
    let promptTitle: String?
    let recordedAt: Date?
    private let stableID: String

    init(run: GuiStatisticsRun, entry: GuiStatisticsEntry) {
        source = .graded
        assignmentTitle = entry.assignmentTitle.isEmpty ? run.assignmentTitle : entry.assignmentTitle
        groupName = entry.groupName ?? run.groupName
        categoryName = entry.categoryName ?? run.categoryName
        exerciseLabel = entry.exerciseLabel ?? run.exerciseLabel
        exerciseNumber = entry.exerciseNumber ?? run.exerciseNumber
        studentName = entry.studentName
        studentProgress = entry.studentProgress
        pointsText = entry.pointsText
        scoreAwarded = entry.scoreAwarded
        scorePossible = entry.scorePossible
        status = entry.status
        runID = run.id
        objectiveText = entry.objectiveText
        targetText = entry.targetText
        answerText = entry.answerText
        modelAnswerText = entry.modelAnswerText
        basisLines = entry.basisLines
        exerciseURL = entry.exerciseURL
        promptTitle = run.promptTitle
        recordedAt = run.recordedAt
        stableID = "\(run.id)|\(entry.id)"
    }

    init(overviewScore: GuiOverviewObservedScore, assignmentTitle: String, groupName: String?) {
        source = .overview
        self.assignmentTitle = assignmentTitle
        self.groupName = groupName
        categoryName = overviewScore.categoryName
        exerciseLabel = overviewScore.exerciseLabel
        exerciseNumber = overviewScore.exerciseNumber
        studentName = overviewScore.studentName
        studentProgress = nil
        pointsText = overviewScore.scoreText
        scoreAwarded = overviewScore.scoreAwarded
        scorePossible = overviewScore.scorePossible
        status = "observed"
        runID = nil
        objectiveText = ""
        targetText = ""
        answerText = ""
        modelAnswerText = ""
        basisLines = []
        exerciseURL = ""
        promptTitle = nil
        recordedAt = nil
        stableID = [
            assignmentTitle,
            groupName ?? "",
            overviewScore.categoryName ?? "",
            overviewScore.exerciseNumber ?? "",
            overviewScore.studentName,
            overviewScore.scoreText,
        ].joined(separator: "|")
    }

    var id: String { dedupeKey }

    var displayStudentName: String {
        studentName.isEmpty ? "Tuntematon opiskelija" : studentName
    }

    var exerciseDisplay: String? {
        let trimmedCategory = categoryName?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfBlank
        let trimmedLabel = exerciseLabel?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfBlank
        let trimmedNumber = exerciseNumber?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfBlank

        if let trimmedCategory, let trimmedNumber {
            return "\(trimmedCategory) · Tehtävä \(trimmedNumber)"
        }
        if let trimmedCategory, let trimmedLabel {
            return "\(trimmedCategory) · \(trimmedLabel)"
        }
        if let trimmedLabel {
            return trimmedLabel
        }
        if let trimmedNumber {
            return "Tehtävä \(trimmedNumber)"
        }
        return nil
    }

    var exerciseSortKey: String {
        exerciseDisplay ?? "Tuntematon tehtävä"
    }

    var scoreRatio: Double? {
        guard let scoreAwarded, let scorePossible, scorePossible > 0 else { return nil }
        return scoreAwarded / scorePossible
    }

    var sourceLabel: String {
        switch source {
        case .graded:
            return "Arvioitu"
        case .overview:
            return "Yleisnäkymä"
        }
    }

    var isOverviewObserved: Bool {
        source == .overview
    }

    var dedupeKey: String {
        [
            assignmentTitle.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            (groupName ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            (categoryName ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            (exerciseLabel ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            (exerciseNumber ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            displayStudentName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
        ].joined(separator: "|")
    }

    func preferred(over existing: StatisticsEntryRecord) -> StatisticsEntryRecord {
        switch (source, existing.source) {
        case (.graded, .overview):
            return self
        case (.overview, .graded):
            return existing
        case (.graded, .graded):
            return (recordedAt ?? .distantPast) >= (existing.recordedAt ?? .distantPast) ? self : existing
        case (.overview, .overview):
            return stableID >= existing.stableID ? self : existing
        }
    }
}

private struct ExerciseSummaryKey: Hashable {
    let examTitle: String
    let exerciseDisplay: String
}

private struct StudentExamPerformanceKey: Hashable {
    let assignmentTitle: String
    let groupName: String?
    let studentName: String
}

private struct StudentExamPerformanceSummary: Identifiable {
    let assignmentTitle: String
    let groupName: String?
    let studentName: String
    let records: [StatisticsEntryRecord]

    var id: String {
        [
            assignmentTitle,
            groupName ?? "",
            studentName,
        ].joined(separator: "|")
    }

    var entryCount: Int {
        records.count
    }

    var exerciseCount: Int {
        Set(records.compactMap(\.exerciseDisplay).filter { !$0.isEmpty }).count
    }

    var gradedEntryCount: Int {
        records.filter { !$0.isOverviewObserved }.count
    }

    var overviewObservedCount: Int {
        records.filter(\.isOverviewObserved).count
    }

    var averageRatio: Double? {
        let ratios = records.compactMap(\.scoreRatio)
        guard !ratios.isEmpty else { return nil }
        return ratios.reduce(0, +) / Double(ratios.count)
    }

    var averageAwarded: Double? {
        let values = records.compactMap(\.scoreAwarded)
        guard !values.isEmpty else { return nil }
        return values.reduce(0, +) / Double(values.count)
    }

    var averagePossible: Double? {
        let values = records.compactMap(\.scorePossible)
        guard !values.isEmpty else { return nil }
        return values.reduce(0, +) / Double(values.count)
    }

    var averagePointsText: String {
        guard let averageAwarded, let averagePossible, averagePossible > 0 else {
            return "-"
        }
        return "\(StatisticsFormatting.decimal(averageAwarded)) / \(StatisticsFormatting.decimal(averagePossible))"
    }

    var bestExerciseDisplay: String? {
        exerciseExtremes.best?.exerciseDisplay
    }

    var weakestExerciseDisplay: String? {
        exerciseExtremes.weakest?.exerciseDisplay
    }

    var exerciseBreakdownText: String {
        let grouped = Dictionary(grouping: records) { $0.exerciseDisplay ?? "Tuntematon tehtävä" }
        let summaries = grouped.keys.sorted().compactMap { exerciseDisplay -> String? in
            let exerciseRecords = grouped[exerciseDisplay] ?? []
            let ratios = exerciseRecords.compactMap(\.scoreRatio)
            let points = exerciseRecords.map(\.pointsText).filter { !$0.isEmpty }
            let averageText = ratios.isEmpty
                ? "-"
                : StatisticsFormatting.percent(ratios.reduce(0, +) / Double(ratios.count))
            let sourceText = exerciseRecords.contains(where: \.isOverviewObserved) ? "yleisnäkymä mukana" : "arvioitu"
            let pointPreview = points.prefix(3).joined(separator: ", ")
            let pointSuffix = points.count > 3 ? ", ..." : ""
            return "\(exerciseDisplay): \(averageText) · \(pointPreview.isEmpty ? "-" : pointPreview + pointSuffix) · \(sourceText)"
        }
        return summaries.isEmpty ? "-" : summaries.joined(separator: "\n")
    }

    private var exerciseExtremes: (best: ExerciseAggregate?, weakest: ExerciseAggregate?) {
        let grouped = Dictionary(grouping: records) { $0.exerciseDisplay ?? "Tuntematon tehtävä" }
        let aggregates = grouped.keys.compactMap { exerciseDisplay -> ExerciseAggregate? in
            let exerciseRecords = grouped[exerciseDisplay] ?? []
            let ratios = exerciseRecords.compactMap(\.scoreRatio)
            guard !ratios.isEmpty else { return nil }
            return ExerciseAggregate(
                exerciseDisplay: exerciseDisplay,
                averageRatio: ratios.reduce(0, +) / Double(ratios.count)
            )
        }
        guard !aggregates.isEmpty else { return (nil, nil) }
        let sorted = aggregates.sorted { leftItem, rightItem in
            if abs(leftItem.averageRatio - rightItem.averageRatio) > 0.0001 {
                return leftItem.averageRatio > rightItem.averageRatio
            }
            return leftItem.exerciseDisplay < rightItem.exerciseDisplay
        }
        return (sorted.first, sorted.last)
    }

    private struct ExerciseAggregate {
        let exerciseDisplay: String
        let averageRatio: Double
    }
}

private struct ExerciseStatisticsSummary: Identifiable {
    let examTitle: String
    let exerciseDisplay: String
    let entryCount: Int
    let uniqueStudentCount: Int
    let averageRatio: Double?
    let interruptedRunCount: Int

    var id: String {
        "\(examTitle)|\(exerciseDisplay)"
    }
}

private struct InterruptedStatisticsSummary: Identifiable {
    let assignmentTitle: String
    let groupName: String?
    let exerciseDisplay: String
    let status: String
    let summary: String

    var id: String {
        "\(assignmentTitle)|\(exerciseDisplay)|\(summary)"
    }
}

private struct StatisticsCard<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.ink)
                Text(subtitle)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.inkMuted)
            }

            content
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Theme.hairline, lineWidth: 1)
        )
        .shadow(color: Theme.shadow, radius: 8, x: 0, y: 4)
    }
}

private struct StatisticsMetricTile: View {
    let title: String
    let value: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
            Text(value)
                .font(.system(size: 26, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.ink)
            Text(subtitle)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(Theme.inkMuted)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Theme.hairline, lineWidth: 1)
        )
        .shadow(color: Theme.shadow, radius: 6, x: 0, y: 3)
    }
}

private struct StatisticsGaugeTile: View {
    let title: String
    let value: Double
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
            Gauge(value: value, in: 0 ... 1) {
                EmptyView()
            } currentValueLabel: {
                Text(StatisticsFormatting.percent(value))
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.ink)
            }
            .gaugeStyle(.accessoryCircularCapacity)
            .tint(Theme.accent)
            Text(subtitle)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(Theme.inkMuted)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Theme.hairline, lineWidth: 1)
        )
        .shadow(color: Theme.shadow, radius: 6, x: 0, y: 3)
    }
}

private struct StatisticsFilterPicker: View {
    let title: String
    @Binding var selection: String
    let options: [String]
    let display: (String) -> String

    init(
        title: String,
        selection: Binding<String>,
        options: [String],
        display: @escaping (String) -> String = { $0 }
    ) {
        self.title = title
        self._selection = selection
        self.options = options
        self.display = display
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased())
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
            Picker(title, selection: $selection) {
                ForEach(options, id: \.self) { option in
                    Text(display(option)).tag(option)
                }
            }
            .pickerStyle(.menu)
            .tint(Theme.ink)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Theme.hairlineSoft, lineWidth: 1)
        )
    }
}

private struct StatisticsMetaPill: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
            Text(value)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(Theme.ink)
                .lineLimit(2)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Theme.hairlineSoft, lineWidth: 1)
        )
    }
}

private struct StatisticsDetailBlock: View {
    let title: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.inkSoft)
            Text(text.isEmpty ? "-" : text)
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(Theme.ink)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct StatisticsAnnotationBubble: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.ink)
            Text(subtitle)
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(Theme.inkMuted)
        }
        .padding(8)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Theme.hairline, lineWidth: 1)
        )
    }
}

private struct StatisticsLogRecord: Identifiable {
    let run: GuiStatisticsRun
    let entry: GuiStatisticsEntry?

    var id: String {
        "\(run.id)|\(entry?.id ?? "run-summary")"
    }

    var runID: String {
        run.id
    }

    var recordedAt: Date {
        run.recordedAt
    }

    var studentName: String {
        guard let entry else { return "Keskeytynyt arviointi" }
        return entry.studentName.isEmpty ? "Tuntematon opiskelija" : entry.studentName
    }

    var studentProgress: String? {
        entry?.studentProgress
    }

    var assignmentTitle: String {
        guard let entry else { return run.assignmentTitle }
        return entry.assignmentTitle.isEmpty ? run.assignmentTitle : entry.assignmentTitle
    }

    var groupName: String? {
        entry?.groupName ?? run.groupName
    }

    var categoryName: String? {
        entry?.categoryName ?? run.categoryName
    }

    var exerciseLabel: String? {
        entry?.exerciseLabel ?? run.exerciseLabel
    }

    var exerciseNumber: String? {
        entry?.exerciseNumber ?? run.exerciseNumber
    }

    var promptTitle: String? {
        run.promptTitle
    }

    var targetText: String {
        entry?.targetText ?? ""
    }

    var answerText: String {
        entry?.answerText ?? ""
    }

    var modelAnswerText: String {
        entry?.modelAnswerText ?? ""
    }

    var submittedPromptText: String? {
        entry?.submittedPromptText?.nilIfBlank ?? entry?.renderedInstructionsText?.nilIfBlank
    }

    var modelResponseText: String? {
        entry?.modelResponseText?.nilIfBlank ?? reasoningText
    }

    var reasoningText: String? {
        let lines = (entry?.basisLines ?? []).filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        return lines.isEmpty ? nil : lines.joined(separator: "\n")
    }

    var modelDisplay: String {
        let provider = entry?.modelProvider?.nilIfBlank
        let name = entry?.modelName?.nilIfBlank
        let reasoning = entry?.reasoningLevel?.nilIfBlank
        let base: String
        switch (provider, name) {
        case (.some(let provider), .some(let name)):
            base = "\(provider) / \(name)"
        case (.none, .some(let name)):
            base = name
        case (.some(let provider), .none):
            base = provider
        case (.none, .none):
            base = "Tuntematon malli"
        }
        if let reasoning {
            return "\(base) / reasoning \(reasoning)"
        }
        return base
    }

    var pointsText: String {
        entry?.pointsText.nilIfBlank ?? (run.interrupted == true ? "Keskeytetty arviointi" : "-")
    }

    var usedHeuristicFallback: Bool {
        entry?.usedHeuristicFallback ?? false
    }

    var fallbackReason: String? {
        entry?.fallbackReason?.nilIfBlank
    }

    var objectiveText: String {
        entry?.objectiveText ?? ""
    }

    var exerciseURL: String? {
        entry?.exerciseURL.nilIfBlank
    }

    var interrupted: Bool {
        run.interrupted == true
    }

}

private struct LogEntryCard: View {
    @EnvironmentObject private var store: GuiStore
    let log: StatisticsLogRecord
    let compact: Bool

    @State private var expanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 12) {
                AdaptiveAxisStack(horizontal: !compact, spacing: 10) {
                    StatisticsMetaPill(label: "Ryhmä", value: log.groupName ?? "-")
                    StatisticsMetaPill(label: "Kategoria", value: log.categoryName ?? "-")
                    StatisticsMetaPill(label: "Tehtävä", value: log.exerciseLabel ?? log.exerciseNumber ?? "-")
                    StatisticsMetaPill(label: "Malli", value: log.modelDisplay)
                    StatisticsMetaPill(label: "Prompti", value: log.promptTitle ?? "-")
                }

                AdaptiveAxisStack(horizontal: !compact, spacing: 10) {
                    StatisticsDetailBlock(title: "Tavoite", text: log.targetText)
                    StatisticsDetailBlock(title: "Oppilaan vastaus", text: log.answerText)
                    StatisticsDetailBlock(title: "Mallivastaus", text: log.modelAnswerText)
                }

                StatisticsDetailBlock(title: "Ohje", text: log.objectiveText)

                LogConversationSection(
                    sender: "GradeAgent lähetti",
                    title: "Lähetetty prompti",
                    bodyText: log.submittedPromptText ?? "Tästä merkinnästä ei ole tallentunut lähetettyä promptia."
                )

                LogConversationSection(
                    sender: modelReplyLabel,
                    title: "Mallin vastaus",
                    bodyText: log.modelResponseText ?? "Tästä merkinnästä ei ole tallentunut raakaa mallivastausta."
                )

                if let fallbackReason = log.fallbackReason {
                    StatisticsDetailBlock(title: "Fallback-syy", text: fallbackReason)
                }

                if let reasoningText = log.reasoningText {
                    StatisticsDetailBlock(title: "Tallennettu perustelu", text: reasoningText)
                }

                if let exerciseURL = log.exerciseURL {
                    StatisticsDetailBlock(title: "Linkki", text: exerciseURL)
                }
            }
            .padding(.top, 12)
        } label: {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(store.visibleStudentName(log.studentName))
                        .font(.system(size: 15, weight: .bold, design: .rounded))
                        .foregroundStyle(Theme.ink)

                    Text(
                        [
                            log.pointsText.nilIfBlank,
                            log.assignmentTitle,
                            log.exerciseLabel ?? log.exerciseNumber,
                        ]
                        .compactMap { $0 }
                        .joined(separator: " · ")
                    )
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.inkMuted)
                    .lineLimit(2)
                }

                Spacer(minLength: 0)

                HStack(spacing: 8) {
                    if log.interrupted {
                        PromptTag(title: "Keskeytetty")
                    }
                    if log.usedHeuristicFallback {
                        PromptTag(title: "Fallback")
                    }
                    PromptTag(title: log.modelDisplay)
                }
            }
        }
        .tint(Theme.ink)
        .padding(16)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Theme.hairline, lineWidth: 1)
        )
        .shadow(color: Theme.shadow, radius: 6, x: 0, y: 3)
    }

    private var modelReplyLabel: String {
        if let modelName = log.entry?.modelName?.nilIfBlank {
            return "\(modelName) vastasi"
        }
        return "Malli vastasi"
    }
}

private struct LogConversationSection: View {
    let sender: String
    let title: String
    let bodyText: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(sender)
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.inkSoft)

            WorkspaceCanvas(title: title, subtitle: "Tarkka loki tästä vaiheesta.") {
                ScrollView {
                    Text(bodyText)
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .foregroundStyle(Theme.ink)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, minHeight: 180, alignment: .topLeading)
        }
    }
}

private enum StatisticsFormatting {
    static func percent(_ value: Double) -> String {
        let normalized = max(0, min(1, value))
        return "\(Int((normalized * 100).rounded())) %"
    }

    static func decimal(_ value: Double) -> String {
        let rounded = (value * 10).rounded() / 10
        if abs(rounded.rounded() - rounded) < 0.001 {
            return String(Int(rounded.rounded()))
        }
        return String(format: "%.1f", rounded)
    }
}

private extension GuiStatisticsEntry {
    var scoreRatio: Double? {
        guard let scoreAwarded, let scorePossible, scorePossible > 0 else {
            return nil
        }
        return scoreAwarded / scorePossible
    }
}

private extension GuiStatisticsRun {
    var averageScoreRatio: Double? {
        let ratios = entries.compactMap(\.scoreRatio)
        guard !ratios.isEmpty else { return nil }
        return ratios.reduce(0, +) / Double(ratios.count)
    }
}

private extension String {
    var nilIfBlank: String? {
        trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : self
    }
}

import SwiftUI
import Charts

struct StatisticsPageView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    @State private var selectedCategory = "Kaikki kategoriat"
    @State private var selectedStatus = "Kaikki tilat"
    @State private var selectedRunID: GuiStatisticsRun.ID?
    @State private var selectedTimelineDate: Date?

    var body: some View {
        GlassCard(fillOpacity: 0.09, strokeOpacity: 0.08) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    if let statisticsErrorMessage = store.statisticsErrorMessage {
                        StatisticsCard(title: "Tilastojen lataus", subtitle: "Tilastosivun tiedot eivät juuri nyt päivittyneet.") {
                            Text(statisticsErrorMessage)
                                .font(.system(size: 13, weight: .medium, design: .rounded))
                                .foregroundStyle(.white.opacity(0.82))
                                .textSelection(.enabled)
                        }
                    }
                    filters
                    metrics

                    if filteredRuns.isEmpty {
                        EmptyStateView(
                            title: "Ei tilastoja",
                            message: "Kun arvioit tehtäviä Ohjaus-sivulla, jokainen ajo tallentuu tänne analysoitavaksi."
                        )
                        .frame(maxWidth: .infinity, minHeight: 320, alignment: .center)
                    } else {
                        chartsSection
                        runTableSection
                        selectedRunSection
                    }
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
                .padding(.bottom, 8)
            }
            .scrollIndicators(.visible)
        }
        .task {
            await store.refreshStatistics()
            if selectedRunID == nil {
                selectedRunID = filteredRuns.first?.id
            }
        }
        .onChange(of: store.statisticsRuns) { _, _ in
            if selectedRun == nil {
                selectedRunID = filteredRuns.first?.id
            }
        }
        .onChange(of: selectedTimelineDate) { _, newValue in
            guard let newValue else { return }
            guard let nearest = timelinePoints.min(by: {
                abs($0.recordedAt.timeIntervalSince(newValue)) < abs($1.recordedAt.timeIntervalSince(newValue))
            }) else {
                return
            }
            selectedRunID = nearest.id
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Tilastot")
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                Text("Tutki arviointiajoja, pistetasoja ja Sanoman DOM:sta kerättyjä tehtäväkohtaisia tietoja.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.76))
            }

            Spacer(minLength: 0)

            Button {
                Task { await store.refreshStatistics() }
            } label: {
                Label("Päivitä", systemImage: "arrow.clockwise")
            }
            .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#7E8A93")))
        }
    }

    private var filters: some View {
        AdaptiveAxisStack(horizontal: !compact, spacing: 12) {
            StatisticsFilterPicker(
                title: "Kategoria",
                selection: $selectedCategory,
                options: ["Kaikki kategoriat"] + categoryOptions
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

    private var metrics: some View {
        AdaptiveAxisStack(horizontal: !compact, spacing: 12) {
            StatisticsMetricTile(title: "Ajot", value: "\(filteredRuns.count)", subtitle: "Tallennetut arvioinnit")
            StatisticsMetricTile(title: "Merkinnät", value: "\(filteredEntryCount)", subtitle: "Yksittäiset oppilasvastaukset")
            StatisticsMetricTile(title: "Oppilaat", value: "\(uniqueStudentCount)", subtitle: "Uniikit opiskelijat")
            StatisticsGaugeTile(title: "Keskiarvo", value: averageScoreRatio, subtitle: "Pisteosuus kaikista merkinnöistä")
        }
    }

    private var chartsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            AdaptiveAxisStack(horizontal: !compact, spacing: 14) {
                StatisticsCard(title: "Pistetaso ajan yli", subtitle: "Lineaarinen kehitys arviointiajojen keskimääräisestä pistetasosta.") {
                    if timelinePoints.isEmpty {
                        EmptyStateView(title: "Ei pistehistoriaa", message: "Tähän ilmestyy lineaarinen näkymä, kun pisteitä on kirjattu.")
                    } else {
                        Chart(timelinePoints) { point in
                            AreaMark(
                                x: .value("Aika", point.recordedAt),
                                y: .value("Pisteosuus", point.averageRatio * 100)
                            )
                            .foregroundStyle(
                                LinearGradient(
                                    colors: [Color(hex: "#AAB5BE").opacity(0.30), Color.clear],
                                    startPoint: .top,
                                    endPoint: .bottom
                                )
                            )

                            LineMark(
                                x: .value("Aika", point.recordedAt),
                                y: .value("Pisteosuus", point.averageRatio * 100)
                            )
                            .foregroundStyle(Color(hex: "#E9EEF2"))
                            .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))

                            PointMark(
                                x: .value("Aika", point.recordedAt),
                                y: .value("Pisteosuus", point.averageRatio * 100)
                            )
                            .foregroundStyle(selectedRunID == point.id ? Color.white : Color(hex: "#D0D7DE"))
                            .symbolSize(selectedRunID == point.id ? 90 : 50)

                            if selectedRunID == point.id {
                                RuleMark(x: .value("Valittu ajo", point.recordedAt))
                                    .foregroundStyle(Color.white.opacity(0.22))
                                    .annotation(position: .top, alignment: .leading) {
                                        StatisticsAnnotationBubble(
                                            title: point.label,
                                            subtitle: point.scoreText
                                        )
                                    }
                            }
                        }
                        .chartLegend(.hidden)
                        .chartYScale(domain: 0 ... 100)
                        .chartXAxis {
                            AxisMarks(values: .automatic(desiredCount: 4))
                        }
                        .chartYAxis {
                            AxisMarks(position: .leading)
                        }
                        .chartXSelection(value: $selectedTimelineDate)
                        .frame(minHeight: 260)
                    }
                }

                StatisticsCard(title: "Kategoriajakauma", subtitle: "Donitsikaavio arvioiduista merkinnöistä kategorioittain.") {
                    if categorySlices.isEmpty {
                        EmptyStateView(title: "Ei kategorioita", message: "Kategoriajakauma näkyy, kun merkintöjä on tallentunut.")
                    } else {
                        Chart(categorySlices) { slice in
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
                StatisticsCard(title: "Ajotilat", subtitle: "Jakautuminen tilan mukaan ilman pylväitä.") {
                    if statusSlices.isEmpty {
                        EmptyStateView(title: "Ei tilatietoja", message: "Tilat näkyvät, kun arviointiajoja on kirjattu.")
                    } else {
                        Chart(statusSlices) { slice in
                            SectorMark(
                                angle: .value("Ajot", slice.value),
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
                            .symbolSize(selectedRunID == point.runID ? 110 : 65)
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

    private var runTableSection: some View {
        StatisticsCard(title: "Ajohistoria", subtitle: "Valitse yksittäinen ajo nähdäksesi oppilas- ja tehtävätason tiedot.") {
            Table(filteredRuns, selection: $selectedRunID) {
                TableColumn("Aika") { run in
                    Text(run.recordedAt, format: .dateTime.day().month().hour().minute())
                }
                TableColumn("Kategoria") { run in
                    Text(run.categoryName ?? "-")
                }
                TableColumn("Tehtävä") { run in
                    Text(run.exerciseLabel ?? "-")
                }
                TableColumn("Merkinnät") { run in
                    Text("\(run.entries.count)")
                }
                TableColumn("Keskiarvo") { run in
                    Text(run.averageScoreRatio.map(StatisticsFormatting.percent) ?? "-")
                }
                TableColumn("Prompti") { run in
                    Text(run.promptTitle ?? "-")
                        .lineLimit(1)
                }
            }
            .frame(minHeight: 240)
        }
    }

    private var selectedRunSection: some View {
        StatisticsCard(title: "Valittu ajo", subtitle: "DOM-muuttujat, pisteet ja perustelut yhdestä arviointiajosta.") {
            if let run = selectedRun {
                VStack(alignment: .leading, spacing: 14) {
                    AdaptiveAxisStack(horizontal: !compact, spacing: 10) {
                        StatisticsMetaPill(label: "Tila", value: localizedStatus(run.status))
                        StatisticsMetaPill(label: "Ryhmä", value: run.groupName ?? "-")
                        StatisticsMetaPill(label: "Tehtävä", value: run.exerciseLabel ?? "-")
                        StatisticsMetaPill(label: "Prompti", value: run.promptTitle ?? "-")
                    }

                    AdaptiveAxisStack(horizontal: !compact, spacing: 10) {
                        StatisticsMetaPill(label: "Yhteenveto", value: run.summary)
                        StatisticsMetaPill(label: "Raportti", value: run.reportPath ?? "-")
                    }

                    if run.entries.isEmpty {
                        EmptyStateView(title: "Ei merkintöjä", message: "Tällä ajolla ei ole tallennettuja oppilaskohtaisia merkintöjä.")
                    } else {
                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(run.entries) { entry in
                                DisclosureGroup {
                                    VStack(alignment: .leading, spacing: 10) {
                                        StatisticsDetailBlock(title: "Tavoite", text: entry.targetText)
                                        StatisticsDetailBlock(title: "Oppilaan vastaus", text: entry.answerText)
                                        StatisticsDetailBlock(title: "Mallivastaus", text: entry.modelAnswerText)
                                        StatisticsDetailBlock(title: "Ohje", text: entry.objectiveText)
                                        StatisticsDetailBlock(title: "Perustelut", text: entry.basisLines.joined(separator: "\n"))
                                        if !entry.exerciseURL.isEmpty {
                                            StatisticsDetailBlock(title: "Linkki", text: entry.exerciseURL)
                                        }
                                    }
                                    .padding(.top, 10)
                                } label: {
                                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text(entry.studentName.isEmpty ? "Tuntematon opiskelija" : entry.studentName)
                                                .font(.system(size: 14, weight: .bold, design: .rounded))
                                                .foregroundStyle(.white)
                                            Text([entry.studentProgress, entry.pointsText, localizedStatus(entry.status)].compactMap { $0 }.joined(separator: " · "))
                                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                                .foregroundStyle(.white.opacity(0.72))
                                        }
                                        Spacer(minLength: 0)
                                        if let ratio = entry.scoreRatio {
                                            Text(StatisticsFormatting.percent(ratio))
                                                .font(.system(size: 12, weight: .bold, design: .rounded))
                                                .foregroundStyle(.white.opacity(0.84))
                                        }
                                    }
                                }
                                .tint(.white)
                                .padding(14)
                                .background(Color.white.opacity(0.05))
                                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                                        .stroke(Color.white.opacity(0.06), lineWidth: 1)
                                )
                            }
                        }
                    }
                }
            } else {
                EmptyStateView(title: "Valitse ajo", message: "Kun valitset ajon taulukosta tai viivakaaviosta, yksityiskohdat näkyvät tässä.")
            }
        }
    }

    private var categoryOptions: [String] {
        Array(Set(store.statisticsRuns.compactMap(\.categoryName))).sorted()
    }

    private var statusOptions: [String] {
        Array(Set(store.statisticsRuns.map(\.status))).sorted()
    }

    private var filteredRuns: [GuiStatisticsRun] {
        store.statisticsRuns.filter { run in
            let categoryMatches = selectedCategory == "Kaikki kategoriat" || run.categoryName == selectedCategory
            let statusMatches = selectedStatus == "Kaikki tilat" || run.status == selectedStatus
            return categoryMatches && statusMatches
        }
    }

    private var filteredEntryCount: Int {
        filteredRuns.reduce(0) { $0 + $1.entries.count }
    }

    private var uniqueStudentCount: Int {
        Set(filteredRuns.flatMap { $0.entries.map(\.studentName) }.filter { !$0.isEmpty }).count
    }

    private var averageScoreRatio: Double {
        let ratios = filteredRuns.flatMap(\.entries).compactMap(\.scoreRatio)
        guard !ratios.isEmpty else { return 0 }
        return ratios.reduce(0, +) / Double(ratios.count)
    }

    private var selectedRun: GuiStatisticsRun? {
        if let selectedRunID {
            return filteredRuns.first(where: { $0.id == selectedRunID }) ?? filteredRuns.first
        }
        return filteredRuns.first
    }

    private var timelinePoints: [StatisticsTimelinePoint] {
        filteredRuns.compactMap { run in
            guard let ratio = run.averageScoreRatio else { return nil }
            return StatisticsTimelinePoint(
                id: run.id,
                recordedAt: run.recordedAt,
                averageRatio: ratio,
                label: run.exerciseLabel ?? run.categoryName ?? "Ajo",
                scoreText: StatisticsFormatting.percent(ratio)
            )
        }
        .sorted { $0.recordedAt < $1.recordedAt }
    }

    private var categorySlices: [StatisticsSlice] {
        let grouped = Dictionary(grouping: filteredRuns.flatMap(\.entries)) { entry in
            entry.categoryName?.isEmpty == false ? entry.categoryName! : "Muu"
        }
        let palette = [
            Color(hex: "#CAD2DA"),
            Color(hex: "#AEB9C4"),
            Color(hex: "#949FAA"),
            Color(hex: "#7C8894"),
            Color(hex: "#65727F"),
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

    private var scatterPoints: [StatisticsScatterPoint] {
        filteredRuns.flatMap { run in
            run.entries.compactMap { entry in
                guard let ratio = entry.scoreRatio,
                      let scorePossible = entry.scorePossible else {
                    return nil
                }
                return StatisticsScatterPoint(
                    id: "\(run.id)|\(entry.id)",
                    runID: run.id,
                    scorePossible: scorePossible,
                    ratio: ratio,
                    color: colorForCategory(entry.categoryName)
                )
            }
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
            return "Kuiva ajo"
        default:
            return status
        }
    }

    private func colorForStatus(_ status: String) -> Color {
        switch status {
        case "completed", "scored":
            return Color(hex: "#92A89A")
        case "needs_review":
            return Color(hex: "#A99E7A")
        case "failed":
            return Color(hex: "#A17F7F")
        case "dry_run":
            return Color(hex: "#8C97A2")
        default:
            return Color(hex: "#BBC4CC")
        }
    }

    private func colorForCategory(_ category: String?) -> Color {
        switch (category ?? "").lowercased() {
        case let value where value.contains("text"):
            return Color(hex: "#D2D9DF")
        case let value where value.contains("kuuntelut"):
            return Color(hex: "#AEB9C4")
        case let value where value.contains("gramm"):
            return Color(hex: "#8D98A4")
        case let value where value.contains("skriv"):
            return Color(hex: "#737F8B")
        default:
            return Color(hex: "#C5CDD4")
        }
    }
}

struct LogsPageView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    @State private var searchText = ""

    var body: some View {
        GlassCard(fillOpacity: 0.09, strokeOpacity: 0.08) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
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
        .searchable(text: $searchText, prompt: "Hae opiskelijaa, tehtävää tai mallia")
        .task {
            await store.refreshStatistics()
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Lokit")
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                Text("Tarkastele jokaista arvioitua oppilasvastausta lokina: DOM-konteksti, lähetetty prompti, käytetty malli ja mallin perustelut.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.76))
            }

            Spacer(minLength: 0)

            Button {
                Task { await store.refreshStatistics() }
            } label: {
                Label("Päivitä", systemImage: "arrow.clockwise")
            }
            .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#7E8A93")))
        }
    }

    private var metrics: some View {
        AdaptiveAxisStack(horizontal: !compact, spacing: 12) {
            StatisticsMetricTile(title: "Lokit", value: "\(filteredLogs.count)", subtitle: "Yksittäiset arviointimerkinnät")
            StatisticsMetricTile(title: "Ajot", value: "\(Set(filteredLogs.map(\.runID)).count)", subtitle: "Lokeissa näkyvät ajot")
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
            run.entries.map { entry in
                StatisticsLogRecord(run: run, entry: entry)
            }
        }
    }
}

private struct StatisticsTimelinePoint: Identifiable {
    let id: String
    let recordedAt: Date
    let averageRatio: Double
    let label: String
    let scoreText: String
}

private struct StatisticsSlice: Identifiable {
    let label: String
    let value: Int
    let color: Color

    var id: String { label }
}

private struct StatisticsScatterPoint: Identifiable {
    let id: String
    let runID: String
    let scorePossible: Double
    let ratio: Double
    let color: Color
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
                    .foregroundStyle(.white)
                Text(subtitle)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.68))
            }

            content
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
        )
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
                .foregroundStyle(.white.opacity(0.58))
            Text(value)
                .font(.system(size: 26, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
            Text(subtitle)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(.white.opacity(0.68))
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
        )
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
                .foregroundStyle(.white.opacity(0.58))
            Gauge(value: value, in: 0 ... 1) {
                EmptyView()
            } currentValueLabel: {
                Text(StatisticsFormatting.percent(value))
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
            }
            .gaugeStyle(.accessoryCircularCapacity)
            Text(subtitle)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(.white.opacity(0.68))
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
        )
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
                .foregroundStyle(.white.opacity(0.58))
            Picker(title, selection: $selection) {
                ForEach(options, id: \.self) { option in
                    Text(display(option)).tag(option)
                }
            }
            .pickerStyle(.menu)
            .tint(.white)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
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
                .foregroundStyle(.white.opacity(0.56))
            Text(value)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.white.opacity(0.88))
                .lineLimit(2)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Color.black.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
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
                .foregroundStyle(.white.opacity(0.62))
            Text(text.isEmpty ? "-" : text)
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.white.opacity(0.86))
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
            Text(subtitle)
                .font(.system(size: 10, weight: .medium, design: .rounded))
        }
        .foregroundStyle(.white)
        .padding(8)
        .background(Color.black.opacity(0.36))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct StatisticsLogRecord: Identifiable {
    let run: GuiStatisticsRun
    let entry: GuiStatisticsEntry

    var id: String {
        "\(run.id)|\(entry.id)"
    }

    var runID: String {
        run.id
    }

    var recordedAt: Date {
        run.recordedAt
    }

    var studentName: String {
        entry.studentName.isEmpty ? "Tuntematon opiskelija" : entry.studentName
    }

    var studentProgress: String? {
        entry.studentProgress
    }

    var assignmentTitle: String {
        entry.assignmentTitle.isEmpty ? run.assignmentTitle : entry.assignmentTitle
    }

    var groupName: String? {
        entry.groupName ?? run.groupName
    }

    var categoryName: String? {
        entry.categoryName ?? run.categoryName
    }

    var exerciseLabel: String? {
        entry.exerciseLabel ?? run.exerciseLabel
    }

    var exerciseNumber: String? {
        entry.exerciseNumber ?? run.exerciseNumber
    }

    var promptTitle: String? {
        run.promptTitle
    }

    var targetText: String {
        entry.targetText
    }

    var answerText: String {
        entry.answerText
    }

    var modelAnswerText: String {
        entry.modelAnswerText
    }

    var submittedPromptText: String? {
        entry.submittedPromptText?.nilIfBlank ?? entry.renderedInstructionsText?.nilIfBlank
    }

    var modelResponseText: String? {
        entry.modelResponseText?.nilIfBlank ?? reasoningText
    }

    var reasoningText: String? {
        let lines = entry.basisLines.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        return lines.isEmpty ? nil : lines.joined(separator: "\n")
    }

    var modelDisplay: String {
        let provider = entry.modelProvider?.nilIfBlank
        let name = entry.modelName?.nilIfBlank
        switch (provider, name) {
        case (.some(let provider), .some(let name)):
            return "\(provider) / \(name)"
        case (.none, .some(let name)):
            return name
        case (.some(let provider), .none):
            return provider
        case (.none, .none):
            return "Tuntematon malli"
        }
    }

    var pointsText: String {
        entry.pointsText
    }

    var usedHeuristicFallback: Bool {
        entry.usedHeuristicFallback ?? false
    }

    var fallbackReason: String? {
        entry.fallbackReason?.nilIfBlank
    }

    var objectiveText: String {
        entry.objectiveText
    }

    var exerciseURL: String? {
        entry.exerciseURL.nilIfBlank
    }
}

private struct LogEntryCard: View {
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
                    Text(log.studentName)
                        .font(.system(size: 15, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)

                    Text(
                        [
                            log.studentProgress,
                            log.pointsText.nilIfBlank,
                            log.exerciseLabel ?? log.exerciseNumber,
                            log.recordedAt.formatted(.dateTime.day().month().hour().minute()),
                        ]
                        .compactMap { $0 }
                        .joined(separator: " · ")
                    )
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.72))
                    .lineLimit(2)
                }

                Spacer(minLength: 0)

                HStack(spacing: 8) {
                    if log.usedHeuristicFallback {
                        PromptTag(title: "Fallback")
                    }
                    PromptTag(title: log.modelDisplay)
                }
            }
        }
        .tint(.white)
        .padding(16)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color.white.opacity(0.07), lineWidth: 1)
        )
    }

    private var modelReplyLabel: String {
        if let modelName = log.entry.modelName?.nilIfBlank {
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
                .foregroundStyle(.white.opacity(0.58))

            WorkspaceCanvas(title: title, subtitle: "Tarkka loki tästä vaiheesta.") {
                ScrollView {
                    Text(bodyText)
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .foregroundStyle(.white.opacity(0.92))
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

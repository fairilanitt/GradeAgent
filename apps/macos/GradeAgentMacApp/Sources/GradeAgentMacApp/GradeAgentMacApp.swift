import AppKit
import SwiftUI

@main
struct GradeAgentMacApp: App {
    @NSApplicationDelegateAdaptor(GradeAgentAppDelegate.self) private var appDelegate
    @StateObject private var store = GuiStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .frame(minWidth: 920, minHeight: 640)
                .task {
                    await store.loadInitialData()
                }
        }
        .defaultSize(width: 1360, height: 880)
        .windowResizability(.contentMinSize)
        .windowStyle(.hiddenTitleBar)
    }
}

final class GradeAgentAppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_: Notification) {
        GuiAPIClient.shutdownSynchronously()
    }
}

struct RootView: View {
    @EnvironmentObject private var store: GuiStore

    var body: some View {
        GeometryReader { proxy in
            let windowWidth = proxy.size.width
            let heroHeight = min(210.0, max(138.0, proxy.size.height * 0.22))
            let compactWindow = windowWidth < 1180
            let sidebarWidth = compactWindow ? 176.0 : 196.0

            ZStack(alignment: .top) {
                LiquidGlassBackground()

                HeroImageOverlayView()
                    .frame(height: heroHeight)
                    .frame(maxWidth: .infinity)
                    .ignoresSafeArea(edges: .top)

                HStack(alignment: .top, spacing: compactWindow ? 14 : 20) {
                    SidebarView(compact: compactWindow)
                        .frame(width: sidebarWidth)
                        .frame(maxHeight: .infinity)

                    VStack(alignment: .leading, spacing: compactWindow ? 14 : 18) {
                        if store.selectedPage == .ohjaus {
                            HeroDashboardView(compact: compactWindow)
                        }
                        Group {
                            switch store.selectedPage {
                            case .ohjaus:
                                ControlPageView(compact: compactWindow)
                            case .kriteerit:
                                CriteriaPageView(compact: compactWindow)
                            case .tilastot:
                                StatisticsPageView(compact: compactWindow)
                            case .lokit:
                                LogsPageView(compact: compactWindow)
                            }
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                    .padding(.top, store.selectedPage == .ohjaus ? 6 : 0)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }
                .padding(.leading, compactWindow ? 8 : 12)
                .padding(.trailing, compactWindow ? 16 : 24)
                .padding(.bottom, compactWindow ? 16 : 24)
                .padding(.top, compactWindow ? 6 : 8)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
        }
    }
}

struct SidebarView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    var body: some View {
        GlassCard(padding: compact ? 12 : 14, fillOpacity: 0.10, strokeOpacity: 0.08) {
            VStack(alignment: .leading, spacing: compact ? 10 : 12) {
                VStack(alignment: .leading, spacing: compact ? 8 : 10) {
                    ForEach(AppPage.allCases) { page in
                        SidebarButton(
                            title: page.title,
                            systemImage: page.systemImage,
                            selected: store.selectedPage == page
                        ) {
                            store.selectedPage = page
                        }
                    }
                }

                Spacer(minLength: 0)

                VStack(alignment: .leading, spacing: compact ? 10 : 12) {
                    if let sessionId = store.sessionId, store.browserReady {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Selainistunto")
                                .font(.system(size: 10, weight: .bold, design: .rounded))
                                .foregroundStyle(.white.opacity(0.62))
                            Text(sessionId)
                                .font(.system(size: 11, weight: .regular, design: .monospaced))
                                .foregroundStyle(.white.opacity(0.72))
                                .textSelection(.enabled)
                        }
                    }

                    if store.hasPrompts {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Kriteerit")
                                .font(.system(size: 10, weight: .bold, design: .rounded))
                                .foregroundStyle(.white.opacity(0.62))
                            Text("\(store.prompts.count) kriteeriä käytettävissä")
                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                .foregroundStyle(.white.opacity(0.76))
                        }
                    }

                    if store.statisticsRunCount > 0 {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Tilastot")
                                .font(.system(size: 10, weight: .bold, design: .rounded))
                                .foregroundStyle(.white.opacity(0.62))
                            Text("\(store.statisticsRunCount) arviointia tallennettu")
                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                .foregroundStyle(.white.opacity(0.76))
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }
}

struct ControlPageView: View {
    @EnvironmentObject private var store: GuiStore
    let compact: Bool

    var body: some View {
        GlassCard(fillOpacity: 0.09, strokeOpacity: 0.08) {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Havaitut tehtävät")
                                .font(.system(size: 20, weight: .bold, design: .rounded))
                                .foregroundStyle(.white)
                            Text("Tämä alareunan työtila näkyy vain Ohjaus-sivulla. Täältä valitaan löydetyt tehtäväsarjat arviointiin.")
                                .font(.system(size: 13, weight: .medium, design: .rounded))
                                .foregroundStyle(.white.opacity(0.76))
                        }
                        Spacer(minLength: 0)
                        if let exerciseCount = store.overview?.exercises.count {
                            Text("\(exerciseCount) tehtävää")
                                .font(.system(size: 12, weight: .bold, design: .rounded))
                                .foregroundStyle(.white.opacity(0.74))
                        }
                    }

                    AdaptiveAxisStack(horizontal: !compact, spacing: 10) {
                        if let overview = store.overview {
                            MiniInfoPill(label: "Koe", value: overview.assignmentTitle)
                            MiniInfoPill(label: "Ryhmä", value: overview.groupName ?? "-")
                            if let answered = overview.studentsAnsweredCount,
                               let total = overview.studentsTotalCount {
                                MiniInfoPill(label: "Oppilaat", value: "\(answered) / \(total)")
                            }
                        }
                        MiniInfoPill(
                            label: "Tunnistus",
                            value: store.browserReady
                                ? (store.isAutoDetectingOverview ? "Automaattinen haku päällä" : "Odottaa yleisnäkymää")
                                : "Selain ei ole auki"
                        )
                        MiniInfoPill(label: "Tila", value: store.latestErrorMessage ?? store.resultMessage)
                    }

                    Divider()
                        .overlay(Color.white.opacity(0.14))
                }

                if let exercises = store.overview?.exercises, !exercises.isEmpty {
                    ScrollView {
                        LazyVGrid(
                            columns: [
                                GridItem(.adaptive(minimum: compact ? 220 : 250, maximum: compact ? 250 : 290), spacing: 14, alignment: .top)
                            ],
                            alignment: .leading,
                            spacing: 14
                        ) {
                            ForEach(exercises) { exercise in
                                ExerciseCardView(exercise: exercise)
                                    .frame(maxWidth: .infinity, minHeight: compact ? 250 : 276, alignment: .topLeading)
                            }
                        }
                        .padding(.bottom, 6)
                    }
                    .scrollIndicators(.hidden)
                } else {
                    EmptyStateView(
                        title: "Ei havaittuja tehtäviä",
                        message: "Kun selain on käynnissä ja avaat Sanoman kokeen yleisnäkymän, arvioimattomat tehtävät ilmestyvät tähän automaattisesti."
                    )
                    .frame(maxHeight: .infinity)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct ExerciseCardView: View {
    @EnvironmentObject private var store: GuiStore
    let exercise: GuiExerciseColumn

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(exercise.title)
                        .font(.system(size: 17, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .lineLimit(2)

                    if let categoryName = exercise.categoryName {
                        PromptTag(title: categoryName)
                    }
                }

                Spacer(minLength: 0)

                PromptTag(title: store.isSelected(exercise) ? "Valittu" : "Valitse")
            }

            VStack(alignment: .leading, spacing: 8) {
                ExerciseInfoLine(label: "Tehtävänumero", value: exercise.exerciseNumber ?? "-")
                ExerciseInfoLine(label: "Arvioimatta", value: "\(exercise.pendingCellCount) / \(exercise.totalCellCount)")
                ExerciseInfoLine(label: "Valmiina", value: "\(exercise.reviewedCellCount) / \(exercise.totalCellCount)")
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Kriteeri")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.white.opacity(0.9))

                Picker("Valittu kriteeri", selection: bindingForPromptSelection) {
                    ForEach(store.prompts) { prompt in
                        Text(prompt.title).tag(prompt.promptId)
                    }
                }
                .labelsHidden()
                .pickerStyle(.menu)
                .tint(.white)

                Text(store.selectedPrompt(for: exercise)?.title ?? "Valitse kriteeri")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.white.opacity(0.74))
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            Spacer(minLength: 0)

            Button {
                Task { await store.gradeExercise(exercise) }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: store.isGrading(exercise) ? "hourglass" : "play.fill")
                    Text(
                        store.isGrading(exercise)
                            ? "Arvioidaan..."
                            : store.isSelected(exercise) ? "Aloita arviointi" : "Valitse tehtävä ensin"
                    )
                        .lineLimit(1)
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(LiquidGlassButtonStyle(tint: Color(hex: "#6F937C")))
            .disabled(store.isGrading(exercise) || !store.hasPrompts || !store.isSelected(exercise))
        }
        .background(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(store.isSelected(exercise) ? Color.white.opacity(0.13) : Color.white.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .stroke(
                    store.isSelected(exercise) ? Color.white.opacity(0.26) : Color.white.opacity(0.12),
                    lineWidth: store.isSelected(exercise) ? 1.3 : 1
                )
        )
        .padding(18)
        .contentShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .onTapGesture {
            store.selectExercise(exercise)
        }
    }

    private var bindingForPromptSelection: Binding<String> {
        Binding(
            get: {
                store.selectedPromptByColumn[exercise.columnKey] ?? store.prompts.first?.promptId ?? ""
            },
            set: { newValue in
                store.setPrompt(newValue, for: exercise.columnKey)
            }
        )
    }
}

struct CriteriaPageView: View {
    let compact: Bool

    var body: some View {
        GlassCard(padding: compact ? 14 : 18, fillOpacity: 0.18, strokeOpacity: 0.08) {
            GeometryReader { proxy in
                let libraryHeight = compact ? 300.0 : 320.0
                let workspaceMinHeight = compact ? 900.0 : 760.0

                ScrollView(.vertical) {
                    VStack(spacing: 14) {
                        PromptLibraryBrowserView(integrated: true)
                            .frame(height: libraryHeight)
                            .frame(maxWidth: .infinity)

                        PromptWorkspaceView(integrated: true)
                            .frame(maxWidth: .infinity, minHeight: workspaceMinHeight, alignment: .top)
                    }
                    .frame(width: proxy.size.width, alignment: .top)
                }
                .scrollIndicators(.visible)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

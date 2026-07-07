/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class RadarDashboard extends Component {
    static template = "radar_drone_vision.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            datasets: 0,
            datasets_ready: 0,
            experiments: 0,
            experiments_trained: 0,
            models: 0,
            models_active: 0,
            inferences: 0,
            inferences_correct: 0,
            hardware: 0,
            hardware_connected: 0,
            recent_experiments: [],
            recent_inferences: [],
            ai_worker_status: 'unknown',
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        try {
            // Datasets
            const datasets = await this.orm.searchCount("radar.dataset", []);
            const datasetsReady = await this.orm.searchCount("radar.dataset", [["state", "=", "ready"]]);

            // Experiments
            const experiments = await this.orm.searchCount("radar.experiment", []);
            const experimentsTrained = await this.orm.searchCount("radar.experiment", [["state", "=", "trained"]]);

            // Models
            const models = await this.orm.searchCount("radar.model", []);
            const modelsActive = await this.orm.searchCount("radar.model", [["is_active", "=", true]]);

            // Inferences
            const inferences = await this.orm.searchCount("radar.inference", []);
            const inferencesCorrect = await this.orm.searchCount("radar.inference", [["is_correct", "=", true]]);

            // Hardware
            const hardware = await this.orm.searchCount("radar.hardware", []);
            const hardwareConnected = await this.orm.searchCount("radar.hardware", [["state", "=", "connected"]]);

            // Recent experiments
            const recentExperiments = await this.orm.searchRead(
                "radar.experiment",
                [["state", "=", "trained"]],
                ["name", "model_type", "accuracy", "eer", "f1_score", "create_date"],
                { limit: 5, order: "create_date desc" }
            );

            // Recent inferences
            const recentInferences = await this.orm.searchRead(
                "radar.inference",
                [],
                ["name", "prediction", "confidence", "is_correct", "create_date"],
                { limit: 10, order: "create_date desc" }
            );

            Object.assign(this.state, {
                datasets,
                datasets_ready: datasetsReady,
                experiments,
                experiments_trained: experimentsTrained,
                models,
                models_active: modelsActive,
                inferences,
                inferences_correct: inferencesCorrect,
                hardware,
                hardware_connected: hardwareConnected,
                recent_experiments: recentExperiments,
                recent_inferences: recentInferences,
            });
        } catch (e) {
            console.error("Dashboard load error:", e);
        }
    }

    get accuracyRate() {
        if (!this.state.inferences) return "N/A";
        return ((this.state.inferences_correct / this.state.inferences) * 100).toFixed(1) + "%";
    }

    openDatasets() {
        this.action.doAction("radar_drone_vision.action_dataset_list");
    }

    openExperiments() {
        this.action.doAction("radar_drone_vision.action_experiment_list");
    }

    openModels() {
        this.action.doAction("radar_drone_vision.action_model_list");
    }

    openInferences() {
        this.action.doAction("radar_drone_vision.action_inference_list");
    }

    openHardware() {
        this.action.doAction("radar_drone_vision.action_hardware_list");
    }

    async refreshData() {
        await this.loadData();
    }
}

registry.category("actions").add("radar_dashboard", RadarDashboard);

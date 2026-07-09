pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        choice(
            name: 'DEPLOY_MODE',
            choices: ['quick', 'full'],
            description: 'quick=热更新前端+重启后端；full=compose build 全量重建'
        )
        string(
            name: 'DEPLOY_HOST',
            defaultValue: '192.168.6.189',
            description: '部署目标服务器 IP'
        )
        string(
            name: 'DEPLOY_DIR',
            defaultValue: '/opt/hlx/QuickNavigation',
            description: '服务器上的项目目录'
        )
    }

    environment {
        COMPOSE_PROJECT_NAME = 'quicknav'
        KAFKA_CONSOLE_PROVIDER = 'kafka-ui'
        // Jenkins 凭据 ID：SSH 私钥，能登录 DEPLOY_HOST
        DEPLOY_SSH_CREDENTIALS = 'quicknav-deploy-ssh'
        NODE_VERSION = '20'
    }

    stages {
        stage('检出代码') {
            steps {
                checkout scm
            }
        }

        stage('构建前端') {
            steps {
                dir('frontend') {
                    sh '''
                        set -e
                        if command -v npm >/dev/null 2>&1; then
                          npm ci
                          npm run build
                        else
                          docker run --rm -v "$PWD:/app" -w /app node:20-alpine sh -c "npm ci && npm run build"
                        fi
                        test -d dist
                        echo "frontend dist ready"
                    '''
                }
            }
        }

        stage('同步到服务器') {
            steps {
                withCredentials([sshUserPrivateKey(
                    credentialsId: "${DEPLOY_SSH_CREDENTIALS}",
                    keyFileVariable: 'SSH_KEY',
                    usernameVariable: 'SSH_USER'
                )]) {
                    sh '''
                        set -e
                        RSYNC_SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
                        DEST="${SSH_USER}@${DEPLOY_HOST}:${DEPLOY_DIR}/"

                        rsync -az --delete \
                          -e "$RSYNC_SSH" \
                          --exclude .git \
                          --exclude node_modules \
                          --exclude frontend/node_modules \
                          --exclude backend/.venv \
                          --exclude offline/docker-images \
                          --exclude "**/__pycache__" \
                          ./ "$DEST"

                        rsync -az \
                          -e "$RSYNC_SSH" \
                          frontend/dist/ "${SSH_USER}@${DEPLOY_HOST}:${DEPLOY_DIR}/frontend/dist/"

                        echo "rsync done"
                    '''
                }
            }
        }

        stage('远程部署') {
            steps {
                withCredentials([sshUserPrivateKey(
                    credentialsId: "${DEPLOY_SSH_CREDENTIALS}",
                    keyFileVariable: 'SSH_KEY',
                    usernameVariable: 'SSH_USER'
                )]) {
                    sh '''
                        set -e
                        FULL_REBUILD=0
                        if [ "$DEPLOY_MODE" = "full" ]; then
                          FULL_REBUILD=1
                        fi

                        ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                          "${SSH_USER}@${DEPLOY_HOST}" \
                          "chmod +x ${DEPLOY_DIR}/scripts/ci/deploy-prod.sh && \
                           DEPLOY_DIR='${DEPLOY_DIR}' \
                           COMPOSE_PROJECT_NAME='${COMPOSE_PROJECT_NAME}' \
                           KAFKA_CONSOLE_PROVIDER='${KAFKA_CONSOLE_PROVIDER}' \
                           FULL_REBUILD='${FULL_REBUILD}' \
                           bash ${DEPLOY_DIR}/scripts/ci/deploy-prod.sh"
                    '''
                }
            }
        }
    }

    post {
        success {
            echo "发布成功: http://${params.DEPLOY_HOST}:8080"
        }
        failure {
            echo '发布失败，请查看 Jenkins 控制台日志'
        }
    }
}
